from dataclasses import dataclass

import ast_nodes as ast
from semantic_errors import SemanticError

# Instâncias reutilizáveis dos tipos escalares "built-in". Comprar tipos (ex: ScalarType("integer") == ScalarType("integer") -> True).
INTEGER = ast.ScalarType("integer")
STRING = ast.ScalarType("string")
BOOLEAN = ast.ScalarType("boolean")

@dataclass(frozen=True)
class Symbol:
    """ Uma entrada na tabela de símbolos:
        - uma variável
        - tipo correspondente
    """
    name: str
    type_spec: ast.TypeSpec

@dataclass(frozen=True)
class FunctionSignature:
    """ Assinatura de uma função definida pelo utilizador:
        - os tipos de cada um dos parâmetros, por ordem
        - o tipo de retorno
    """
    param_types: list[ast.TypeSpec]
    return_type: ast.TypeSpec

class SymbolTable:
    """ O programa principal tem o seu conjunto de variáveis, e cada função
    tem o seu próprio conjunto separado (parâmetros + variáveis locais),
    sem interferirem uns com os outros """

    def __init__(self) -> None:
        # inicia com apenas um dicionário vazio (âmbito global)
        self._scopes: list[dict[str, Symbol]] = [{}]

    def push_scope(self) -> None:
        # quando entra no corpo de uma function, empilha um novo dicionário vazio
        self._scopes.append({})

    def pop_scope(self) -> None:
        # remove esse dicionário, e é como se a função "esquecesse" as suas variáveis locais
        self._scopes.pop()

    def declare(self, name: str, type_spec: ast.TypeSpec) -> None:
        # verifica duplicados dentro do mesmo âmbito (não em todos)
        # permite que uma função tenha um parâmetro i, mesmo que já exista uma variável global i
        scope = self._scopes[-1]
        if name in scope:
            raise SemanticError(f"Variável '{name}' declarada mais do que uma vez")
        scope[name] = Symbol(name, type_spec)

    def lookup(self, name: str) -> Symbol:
        # procura do âmbito mais interno (topo da pilha) para o mais externo (o global), para que o corpo de
        # uma função também consiga ver as variáveis globais
        for scope in reversed(self._scopes):
            if name in scope:
                return scope[name]
        raise SemanticError(f"Variável '{name}' não declarada")

class SemanticAnalyzer:
    def __init__(self) -> None:
        self.symbols = SymbolTable()
        # assinaturas de todas as functions do utilizador, para verifica:
        #   - nº argumentos
        #   - tipos
        #   - tipo de retorno
        self.functions: dict[str, FunctionSignature] = {}

    def analyze(self, program: ast.Program) -> None:
        """ Analisa o bloco principal do programa, e lança SemanticError na primeira inconsistência encontrada;
        se não for lançada nenhuma exceção, então o programa é semanticamente válido. """
        self._visit_block(program.block)


    # Blocos e Declarações
    def _visit_block(self, block: ast.Block) -> None:
        # 1. Declara todas as variáveis deste bloco
        for declaration in block.declarations:
            self._declare_vars(declaration)

        # 2. Regista a assinatura de cada função ANTES de analisar o corpo de qualquer uma delas,
        # para permitir (no futuro, embora não seja usado nestes exemplos) que uma função chame
        # outra, declarada mais tarde no mesmo bloco
        for subprogram in block.subprograms:
            self._register_function_signature(subprogram)
        for subprogram in block.subprograms:
            self._visit_subprogram(subprogram)

        # 3. Depois de tudo declarado, analisa o corpo (begin ... end)
        self._visit_statement(block.compound)

    def _declare_vars(self, declaration: ast.VarDecl) -> None:
        self._validate_type(declaration.type_spec)
        for name in declaration.names:
            self.symbols.declare(name, declaration.type_spec)

    def _validate_type(self, type_spec: ast.TypeSpec) -> None:
        """ Confirma se um TypeSpec (de uma declaração, um parâmetro ou retorno) é um tipo válido e bem formado. """
        if isinstance(type_spec, ast.ScalarType):
            if type_spec.name not in {"integer", "string", "boolean"}:
                raise SemanticError(f"Tipo desconhecido: {type_spec.name}")
            return
        if isinstance(type_spec, ast.ArrayType):
            if type_spec.first > type_spec.last:
                raise SemanticError("Array com limite inferior maior do que o limite superior")
            self._validate_type(type_spec.element_type)
            return
        raise SemanticError(f"Tipo inválido: '{type_spec}'")

    # SubProgramas (Functions)
    def _register_function_signature(self, subprogram: ast.SubProgramDecl) -> None:
        """ Calcula e guarda a assinatura da função (tipos dos parâmetros + tipo de retorno), sem ainda analisar o corpo.
        Feito à parte de _visit_subprogram para que a assinatura já esteja disponível antes de qualquer função ser chamada. """
        if subprogram.name in self.functions:
            raise SemanticError(f"Função '{subprogram.name}' declarada mais do que uma vez")
        if subprogram.return_type is None:
            # A gramática só produz functions
            raise SemanticError("Procedimentos sem tipo de retorno não são suportados")
        self._validate_type(subprogram.return_type)

        param_types: list[ast.TypeSpec] = []
        for param in subprogram.params:
            self._validate_type(param.type_spec)
            # Um Param pode agrupar vários nomes do mesmo tipo (ex: a, b, c: integer), por isso repete-se o tipo uma vez por cada nome
            param_types.extend([param.type_spec] * len(param.names))

        self.functions[subprogram.name] = FunctionSignature(
            param_types=param_types,
            return_type=subprogram.return_type
        )

    def _visit_subprogram(self, subprogram: ast.SubProgramDecl) -> None:
        """ Analisa o corpo de uma função, no seu próprio âmbito isolado. """
        signture = self.functions[subprogram.name]
        self.symbols.push_scope()
        try:
            # O próprio nome da função, dentro do seu corpo, funciona como uma variável do tipo de retorno
            self.symbols.declare(subprogram.name, signture.return_type)
            for param in subprogram.params:
                for name in param.names:
                    self.symbols.declare(name, param.type_spec)
            # O corpo da função é ele próprio um "block" completo, com as suas próprias declarações locais + instruções
            self._visit_block(subprogram.block)
        finally:
            # Garante que o âmbito é sempre removido, mesmo que a análise do corpo lance um erro pelo meio
            self.symbols.pop_scope()


    # Instruções
    def _visit_statement(self, statement: ast.Statement) -> None:
        if isinstance(statement, ast.Compound):
            for child in statement.statements:
                self._visit_statement(child)
            return

        if isinstance(statement, ast.Assign):
            # o tipo do lado esquerdo (target) e do lado direito (value) têm de ser exatamente iguais
            target_type = self._infer_target(statement.target)
            value_type = self._infer_expression(statement.value)
            self._require_same_type(target_type, value_type, "atribuicao")
            return

        if isinstance(statement, ast.ProcedureCall):
            self._visit_procedure_call(statement)
            return

        if isinstance(statement, ast.If):
            self._require_type(self._infer_expression(statement.condition), BOOLEAN, "condicao do if")
            self._visit_statement(statement.then_)
            if statement.else_ is not None:
                self._visit_statement(statement.else_)
            return

        if isinstance(statement, ast.While):
            self._require_type(self._infer_expression(statement.condition), BOOLEAN, "condicao do while")
            self._visit_statement(statement.body)
            return

        if isinstance(statement, ast.For):
            var_symbol = self.symbols.lookup(statement.variable)
            self._require_type(var_symbol.type_spec, INTEGER, "variavel de controlo do for")
            self._require_type(self._infer_expression(statement.start), INTEGER, "inicio do for")
            self._require_type(self._infer_expression(statement.stop), INTEGER, "limite do for")
            self._visit_statement(statement.body)
            return

        if isinstance(statement, ast.NoOp):
            # instrução vazia -> nada a verificar
            return

        raise SemanticError(f"Instrução não suportada: '{statement}'")

    def _visit_procedure_call(self, call: ast.ProcedureCall) -> None:
        # A gramática só produz ProcedureCall para writeln/readln
        # chamada a funções do utilizador são sempre FuncCall
        if call.name == "writeln":
            for arg in call.args:
                self._require_scalar(self._infer_expression(arg), "writeln")
            return

        if call.name == "readln":
            for arg in call.args:
                if not isinstance(arg, (ast.Variable, ast.ArrayAccess)):
                    raise SemanticError("readln só aceita variáveis como argumentos")
                self._require_scalar(self._infer_target(arg), "readln")
            return

        raise SemanticError(f"Procedimento desconhecido: '{call.name}'")

    # Alvos de atribuição (lado esquerdo do :=)
    def _infer_target(self, target: ast.Variable | ast.ArrayAccess) -> ast.TypeSpec:
        if isinstance(target, ast.Variable):
            symbol = self.symbols.lookup(target.name)
            if isinstance(symbol.type_spec, ast.ArrayType):
                # só se pode atribuir a uma posição do array de cada vez
                raise SemanticError(f"Array '{target.name}' precisa de índice")
            return symbol.type_spec

        if isinstance(target, ast.ArrayAccess):
            return self._infer_array_access(target)

        raise SemanticError(f"Alvo de atribuição inválido: '{target}'")


    # Expressões
    def _infer_expression(self, expression: ast.Expression) -> ast.TypeSpec:
        if isinstance(expression, ast.IntLiteral):
            return INTEGER
        if isinstance(expression, ast.StringLiteral):
            return STRING
        if isinstance(expression, ast.BoolLiteral):
            return BOOLEAN

        if isinstance(expression, ast.Variable):
            symbol = self.symbols.lookup(expression.name)
            if isinstance(symbol.type_spec, ast.ArrayType):
                # Utilizar um array sem índice não é uma expressão válida
                raise SemanticError(f"Array '{expression.name}' precisa de índice")
            return symbol.type_spec

        if isinstance(expression, ast.ArrayAccess):
            return self._infer_array_access(expression)

        if isinstance(expression, ast.BinaryOp):
            return self._infer_binary(expression)

        if isinstance(expression, ast.FuncCall):
            return self._infer_funccall(expression)

        raise SemanticError(f"Expressão não suportada: '{expression}'")


    def _infer_array_access(self, access: ast.ArrayAccess) -> ast.TypeSpec:
        """ Trata tanto array[i], como string[i] (indexar uma string, devolve um "carácter").
        Como a minha AST não tem um tipo char separadamente, um carácter é representado como STRING. """
        symbol = self.symbols.lookup(access.name)

        if symbol.type_spec == STRING:
            self._require_type(self._infer_expression(access.index), INTEGER, "índice da string")
            return STRING

        if not isinstance(symbol.type_spec, ast.ArrayType):
            raise SemanticError(f"Variável '{access.name}' não é um array, nem uma string")
        self._require_type(self._infer_expression(access.index), INTEGER, "índice do array")
        return symbol.type_spec.element_type

    def _infer_binary(self, expression: ast.BinaryOp) -> ast.TypeSpec:
        left_type = self._infer_expression(expression.left)
        right_type = self._infer_expression(expression.right)
        op = expression.op  # valores reais produzidos pelo parser ("+", "-", "*", "div", "mod", ...)

        if op in {"+", "-", "*", "div", "mod"}:
            # operadores aritméticos: ambos os lados integer, resultado integer
            self._require_type(left_type,INTEGER, f"operador '{op}'")
            self._require_type(right_type, INTEGER, f"operador '{op}'")
            return INTEGER

        if op in {"and", "or"}:
            # operadores lógicos: ambos os lados boolean, resultado boolean
            self._require_type(left_type, BOOLEAN, f"operador '{op}'")
            self._require_type(right_type, BOOLEAN, f"operador '{op}'")
            return BOOLEAN

        if op in {"=", "<>"}:
            # igualdade/desigualdade: ambos os lados têm de ter o MESMO tipo
            self._require_same_type(left_type, right_type, f"operador '{op}'")
            self._require_scalar(left_type, f"operador '{op}'")
            return BOOLEAN

        if op in {"<", "<=", ">", ">="}:
            # comparações: apenas entre integers
            self._require_type(left_type, INTEGER, f"operador '{op}'")
            self._require_type(right_type, INTEGER, f"operador '{op}'")
            return BOOLEAN

        raise SemanticError(f"Operador binário desconhecido: '{op}'")


    def _infer_funccall(self, call: ast.FuncCall) -> ast.TypeSpec:
        # 'length' é uma função embutida do Pascal, onde recebe uma string e devolve o seu comprimento (integer).
        if call.name == "length":
            if len(call.args) != 1:
                raise SemanticError("Função 'length' espera exatamente 1 argumento")
            self._require_type(self._infer_expression(call.args[0]), STRING, "argumento de 'length'")
            return INTEGER

        if call.name not in self.functions:
            raise SemanticError(f"Função desconhecida: '{call.name}'")

        # verifica se o nº de argumentos e o tipo de cada um correspondem com a assinatura registada em _register_function_signature
        signature = self.functions[call.name]
        if len(call.args) != len(signature.param_types):
            raise SemanticError(f"Função '{call.name}' espera {len(signature.param_types)} argumentos, mas recebeu {len(call.args)}")
        for i, (arg, expected_type) in enumerate(zip(call.args, signature.param_types), start=1):
            actual_type = self._infer_expression(arg)
            self._require_same_type(actual_type, expected_type, f"argumento {i} de '{call.name}'")

        return signature.return_type


    # Auxiliares de verificação de tipos
    def _require_type(self, actual: ast.TypeSpec, expected: ast.TypeSpec, context: str) -> None:
        """ Verifica que 'actual' é exatamente o mesmo tipo que 'expected' """
        if actual != expected:
            raise SemanticError(f"Tipo inválido em {context}: obtido {format_type(actual)} e esperado {format_type(expected)}")

    def _require_same_type(self, left: ast.TypeSpec, right: ast.TypeSpec, context: str) -> None:
        """ Verifica que 'left' e 'right' são o mesmo tipo. """
        if left != right:
            raise SemanticError(f"Tipos incompatíveis em {context}: {format_type(left)} vs {format_type(right)}")

    def _require_scalar(self, type_spec: ast.TypeSpec, context: str) -> None:
        """ Verifica que o tipo NÃO é um array (é integer/string/boolean) """
        if not isinstance(type_spec, ast.ScalarType):
            raise SemanticError(f"{context} espera valor escalar, mas recebeu array")

def format_type(type_spec: ast.TypeSpec) -> str:
    """ Converte um TypeSpec numa string legível, para utilizar nas mensagens de erro. """
    if isinstance(type_spec, ast.ScalarType):
        return type_spec.name
    if isinstance(type_spec, ast.ArrayType):
        return f"array[{type_spec.first}..{type_spec.last}] of {format_type(type_spec.element_type)}"
    return repr(type_spec)