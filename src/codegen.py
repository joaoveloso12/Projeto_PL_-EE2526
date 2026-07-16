from dataclasses import dataclass, field

import ast_nodes as ast

INTEGER = ast.ScalarType("integer")
STRING = ast.ScalarType("string")
BOOLEAN = ast.ScalarType("boolean")


class CodeGenError(Exception):
    pass


@dataclass
class FunctionFrame:
    """ Mapa de nomes -> deslocamento (offset) relativo ao function frame, para dentro do corpo de uma função.
    param_offset: nome do parâmetro -> offset negativo (ex: -1, -2, ...)
    local_offset: nome da variável local -> offset não negativo (ex: 0, 1, 2,...)
    return_offset: offset (negativo) do "slot" onde a função guarda o seu valor de retorno
    return_name: o próprio nome da função ( para reconhecer a atribuição NomeFuncao := valor)
    """
    param_offset: dict[str, int] = field(default_factory=dict)
    local_offset: dict[str, int] = field(default_factory=dict)
    return_offset: int = 0
    return_name: str = ""


class CodeGenerator:
    """ Percorre a AST e vai acumulando instruções da EWVM em self.instructions. """
    def __init__(self) -> None:
        self.instructions: list[str] = []
        self._label_counter = 0
        # nome -> (índice, TypeSpec) para variáveis globais
        self.global_vars: dict[str, tuple[int, ast.TypeSpec]] = {}
        # nome -> TypeSpec para variáveis locais/parametros da function atual
        self.local_types: dict[str, ast.TypeSpec] = {}
        # None enquanto estivermos a gerar código do programa principal; e passa a ter um FunctionFrame enquanto se gera o código do corpo de uma função
        self.frame: FunctionFrame | None = None


    # Utilidades
    def emit(self, instruction: str) -> None:
        """ Acrescenta uma linha de instrução à lista de código gerado. """
        self.instructions.append(instruction)

    def new_label(self, prefix: str = "L") -> str:
        """ Gera um rótulo único (ex: 'if3', 'endwhile7', ...) para nunca colidir com rótulos de outras
        instruções if/while/for, mesmo quando há vários no mesmo programa. """
        self._label_counter += 1
        return f"{prefix}{self._label_counter}"

    # Ponto de entrada
    def generate(self, program: ast.Program) -> list[str]:
        """ Gera o código completo para um Program. Devolve a lista de instruções, uma por linha, pronta
        a escrever num ficheiro .vm """
        self._collect_globals(program.block.declarations)

        self.emit("START")
        if self.global_vars:
            self.emit(f"PUSHN {len(self.global_vars)}")
        self._alloc_global_arrays()

        # As funções são geradas ANTES do corpo principal, mas o fluxo de execução tem de "saltar por cima delas", i.e.,
        # só devem correr quando são chamadas via CALL.
        main_label = self.new_label("main")
        self.emit(f"JUMP {main_label}")
        for subprogram in program.block.subprograms:
            self._gen_subprogram(subprogram)
        self.emit(f"{main_label}:")
        self._gen_statement(program.block.compound)
        self.emit("STOP")
        return self.instructions

    def _collect_globals(self, declarations: list[ast.VarDecl]) -> None:
        """ Atribui um índice a cada variável global, pela ordem que são declaradas no código fonte."""
        for decl in declarations:
            for name in decl.names:
                index = len(self.global_vars)
                self.global_vars[name] = (index, decl.type_spec)

    def _alloc_global_arrays(self) -> None:
        """ Para cada variável global do tipo array, é alocado um bloco na heap (ALLOCN) uma única vez, logo no arranque
        do programa, e guarda o endereço devolvido no slot dessa variável. Depois esse endereço é reutilizado em todos os
        acessos (LOADN/STOREN) ao longo do programa. """
        for name, (index, type_spec) in self.global_vars.items():
            if isinstance(type_spec, ast.ArrayType):
                size = type_spec.last - type_spec.first + 1
                self.emit(f"PUSHI {size}")
                self.emit("ALLOCN")
                self.emit(f"STOREG {index}")


    # SubProgramas
    def _gen_subprogram(self, subprogram: ast.SubProgramDecl) -> None:
        """ Gera o código de uma function, atribúi um rótulo com o seu nome, reserva espaço para as variáveis locais, corpo,
        e RETURN. Os parâmetros ficam em offsets negativos (fp[-1], fp[-2], ...), o valor de retorno num offset ainda mais
        negativo, e as variáveis locais em offsets positivos.
        """
        flat_params: list[str] = []
        for param in subprogram.params:
            flat_params.extend(param.names)

        n = len(flat_params)
        frame = FunctionFrame(return_offset=-(n + 1), return_name=subprogram.name)
        for i, pname in enumerate(flat_params):
            # último parâmetro -> fp[-1], primeiro -> fp[-n]
            frame.param_offset[pname] = -(n - i)

        local_names: list[str] = []
        for decl in subprogram.block.declarations:
            local_names.extend(decl.names)
        for i, lname in enumerate(local_names):
            frame.local_offset[lname] = i

        # tipos (para saber INTEGER/STRING/BOOLEAN em cada acesso)
        # preciso para saber se é WRITEI ou WRITES
        local_types: dict[str, ast.TypeSpec] = {}
        param_types: dict[str, ast.TypeSpec] = {}
        pi = 0
        for param in subprogram.params:
            for _ in param.names:
                param_types[flat_params[pi]] = param.type_spec
                pi += 1
        for decl in subprogram.block.declarations:
            for name in decl.names:
                local_types[name] = decl.type_spec

        self.emit(f"{subprogram.name}:")
        if local_names:
            self.emit(f"PUSHN {len(local_names)}")

        old_frame, old_types = self.frame, self.local_types
        self.frame = frame
        self.local_types = {**param_types, **local_types,
                             subprogram.name: subprogram.return_type}
        try:
            self._gen_statement(subprogram.block.compound)
        finally:
            self.frame, self.local_types = old_frame, old_types

        self.emit("RETURN")

    # Resolução de variáveis (endereçamento)
    def _var_type(self, name: str) -> ast.TypeSpec:
        """ Devolve o TypeSpec de uma variável, procurando primeiro no âmbito local (se estivermos numa
        function) e depois no âmbito global. """
        if self.frame is not None and name in self.local_types:
            return self.local_types[name]
        if name in self.global_vars:
            return self.global_vars[name][1]
        raise CodeGenError(f"Variavel '{name}' desconhecida no codegen")

    def _gen_push_var(self, name: str) -> None:
        """ Emite a instrução para empilhar o VALOR atual de uma variável (PUSHG para globais, PUSHL para
        locais/parâmetros/slot de retorno da função atual). """
        if self.frame is not None and name == self.frame.return_name:
            self.emit(f"PUSHL {self.frame.return_offset}")
        elif self.frame is not None and name in self.frame.param_offset:
            self.emit(f"PUSHL {self.frame.param_offset[name]}")
        elif self.frame is not None and name in self.frame.local_offset:
            self.emit(f"PUSHL {self.frame.local_offset[name]}")
        elif name in self.global_vars:
            self.emit(f"PUSHG {self.global_vars[name][0]}")
        else:
            raise CodeGenError(f"Variavel '{name}' desconhecida no codegen")

    def _gen_store_var(self, name: str) -> None:
        """ Emite a instrução para guardar o valor do topo da pilha numa variável (STOREG/STOREL). """
        if self.frame is not None and name == self.frame.return_name:
            self.emit(f"STOREL {self.frame.return_offset}")
        elif self.frame is not None and name in self.frame.param_offset:
            self.emit(f"STOREL {self.frame.param_offset[name]}")
        elif self.frame is not None and name in self.frame.local_offset:
            self.emit(f"STOREL {self.frame.local_offset[name]}")
        elif name in self.global_vars:
            self.emit(f"STOREG {self.global_vars[name][0]}")
        else:
            raise CodeGenError(f"Variavel '{name}' desconhecida no codegen")

    # Instruções
    def _gen_statement(self, statement: ast.Statement) -> None:
        """ Encaminha cada tipo de nó Statement para o gerador correspondente. """
        if isinstance(statement, ast.Compound):
            for stmt in statement.statements:
                self._gen_statement(stmt)
            return

        if isinstance(statement, ast.NoOp):
            # instrução vazia -> não gera nada
            return

        if isinstance(statement, ast.Assign):
            self._gen_assign(statement)
            return

        if isinstance(statement, ast.ProcedureCall):
            self._gen_procedure_call(statement)
            return

        if isinstance(statement, ast.If):
            self._gen_if(statement)
            return

        if isinstance(statement, ast.While):
            self._gen_while(statement)
            return

        if isinstance(statement, ast.For):
            self._gen_for(statement)
            return

        raise CodeGenError(f"Instrução nao suportada no codegen: '{statement}'")

    def _gen_assign(self, statement: ast.Assign) -> None:
        """ Gera código para 'target := value'.
        Para uma variável simples, faz <valor> STOREG/STOREL.
        Para uma posição de array (números[i] := valor), STOREN espera, e o valor é gerado só no FINAL, ao contrário das variáveis simples.
        """
        target = statement.target
        if isinstance(target, ast.Variable):
            self._gen_expr(statement.value)
            self._gen_store_var(target.name)
            return

        if isinstance(target, ast.ArrayAccess):
            array_type = self._var_type(target.name)
            assert isinstance(array_type, ast.ArrayType)
            self._gen_push_var(target.name)                         # endereco (a)
            self._gen_index_offset(target.index, array_type.first)  # deslocamento (n)
            self._gen_expr(statement.value)                         # valor (v)
            self.emit("STOREN")
            return

        raise CodeGenError(f"Alvo de atribuicao nao suportado: '{target}'")

    def _gen_index_offset(self, index_expr: ast.Expression, first: int) -> None:
        self._gen_expr(index_expr)
        if first != 0:
            self.emit(f"PUSHI {first}")
            self.emit("SUB")

    def _gen_procedure_call(self, call: ast.ProcedureCall) -> None:
        """writeln e readln são os únicos ProcedureCall que a gramática produz (as chamadas das functions do utilizador
        são FuncCall, e são tratadas em _gen_funccall). """
        if call.name == "writeln":
            # WRITEI para integer, e WRITES para string, e no final sempre a mudança de linha com WRITELN
            for arg in call.args:
                arg_type = self._infer_type(arg)
                self._gen_expr(arg)
                if arg_type == STRING:
                    self.emit("WRITES")
                else:
                    self.emit("WRITEI")
            self.emit("WRITELN")
            return

        if call.name == "readln":
            for arg in call.args:
                self._gen_readln_target(arg)
            return

        raise CodeGenError(f"Procedimento nao suportado no codegen: '{call.name}'")

    def _gen_readln_target(self, target: ast.Expression) -> None:
        """ Gera o código para ler um valor do teclado (READ, que devolve sempre uma string) e guardá-lo na variável/posição
         de array indicada, convertendo para um integer com ATOI quando necessário. """
        if isinstance(target, ast.Variable):
            var_type = self._var_type(target.name)
            self.emit("READ")
            if var_type == INTEGER:
                self.emit("ATOI")
            self._gen_store_var(target.name)
            return

        if isinstance(target, ast.ArrayAccess):
            # o endereço e o deslocamento são gerados ANTES do valor lido, por causa da ordem exigida por STOREN
            array_type = self._var_type(target.name)
            assert isinstance(array_type, ast.ArrayType)
            self._gen_push_var(target.name)
            self._gen_index_offset(target.index, array_type.first)
            self.emit("READ")
            if array_type.element_type == INTEGER:
                self.emit("ATOI")
            self.emit("STOREN")
            return

        raise CodeGenError(f"Alvo de readln não suportado: '{target}'")

    def _gen_if(self, statement: ast.If) -> None:
        """ Gera código para 'if condition then then_ [else else_]'.
        Sem else:
            <condição> JZ end <then_> end:
        Com else:
            <condição> JZ else <then_> JUMP end else: <else_> end:
        """
        self._gen_expr(statement.condition)
        if statement.else_ is None:
            end_label = self.new_label("endif")
            self.emit(f"JZ {end_label}")
            self._gen_statement(statement.then_)
            self.emit(f"{end_label}:")
        else:
            else_label = self.new_label("else")
            end_label = self.new_label("endif")
            self.emit(f"JZ {else_label}")
            self._gen_statement(statement.then_)
            self.emit(f"JUMP {end_label}")
            self.emit(f"{else_label}:")
            self._gen_statement(statement.else_)
            self.emit(f"{end_label}:")

    def _gen_while(self, statement: ast.While) -> None:
        """Gera código para 'while condition do body':
            start:  <condição>  JZ end  <body>  JUMP start  end:
        """
        start_label = self.new_label("while")
        end_label = self.new_label("endwhile")
        self.emit(f"{start_label}:")
        self._gen_expr(statement.condition)
        self.emit(f"JZ {end_label}")
        self._gen_statement(statement.body)
        self.emit(f"JUMP {start_label}")
        self.emit(f"{end_label}:")

    def _gen_for(self, statement: ast.For) -> None:
        """Gera código para 'for variable := start to/downto stop do body'.

        Começa com inicialização (variable := start) + um ciclo while implícito que testa 'variable <= stop' (to) ou
        'variable >= stop' (downto), executa o corpo, e depois incrementa/decrementa a variável de controlo.
        A paragem ('stop') é reavaliada a cada iteração (não é guardada numa variável temporária), porque em nenhum
        exemplo do enunciado 'stop' tem efeitos secundários (é sempre uma variável ou uma constante).
        """
        # inicializacao: variavel := start
        self._gen_expr(statement.start)
        self._gen_store_var(statement.variable)

        start_label = self.new_label("for")
        end_label = self.new_label("endfor")
        self.emit(f"{start_label}:")

        # condição de continuação: variável <= stop (to) ou variável >= stop (downto)
        self._gen_push_var(statement.variable)
        self._gen_expr(statement.stop)
        self.emit("SUPEQ" if statement.downto else "INFEQ")
        self.emit(f"JZ {end_label}")

        self._gen_statement(statement.body)

        # incremento/decremento
        self._gen_push_var(statement.variable)
        self.emit("PUSHI 1")
        self.emit("SUB" if statement.downto else "ADD")
        self._gen_store_var(statement.variable)

        self.emit(f"JUMP {start_label}")
        self.emit(f"{end_label}:")

    # Expressões
    def _is_char_expr(self, expr: ast.Expression) -> bool:
        if isinstance(expr, ast.StringLiteral):
            return True
        if isinstance(expr, ast.ArrayAccess):
            return self._var_type(expr.name) == STRING
        return False

    def _gen_char_value(self, expr: ast.Expression) -> None:
        """ Gera código que deixa no topo da pilha o código ASCII (um integer) do carácter representado por expr, utilizando
        CHRCODE para uma string literal (o seu primeiro carácter), ou CHARAT para indexar uma variável string numa posição.

        A posição do CHARAT da VM é 0-indexada, e como o Pascal indexa strings a partir de 1, subtrai-se 1 ao índice antes de
        chamar CHARAT.
        """
        if isinstance(expr, ast.StringLiteral):
            self._emit_pushs(expr.value)
            self.emit("CHRCODE")
            return
        if isinstance(expr, ast.ArrayAccess):
            array_var_type = self._var_type(expr.name)
            assert array_var_type == STRING
            self._gen_push_var(expr.name)
            # assume-se indexacao 0-based no CHARAT da VM; Pascal usa 1-based
            self._gen_expr(expr.index)
            self.emit("PUSHI 1")
            self.emit("SUB")
            self.emit("CHARAT")
            return
        raise CodeGenError(f"Expressão de carácter não suportada: '{expr}'")

    def _emit_pushs(self, text: str) -> None:
        """Emite PUSHS com o texto devidamente escapado. """

        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        self.emit(f'PUSHS "{escaped}"')

    def _gen_expr(self, expr: ast.Expression) -> None:
        """ Encaminha cada tipo de nó Expression para o seu gerador correspondente,e no final deixa sempre exatamente o valor
        dessa expressão valor no topo da pilha. """
        if isinstance(expr, ast.IntLiteral):
            self.emit(f"PUSHI {expr.value}")
            return
        if isinstance(expr, ast.BoolLiteral):
            # Pascal 'true'/'false' representados como inteiros 1/0
            self.emit(f"PUSHI {1 if expr.value else 0}")
            return
        if isinstance(expr, ast.StringLiteral):
            self._emit_pushs(expr.value)
            return
        if isinstance(expr, ast.Variable):
            self._gen_push_var(expr.name)
            return
        if isinstance(expr, ast.ArrayAccess):
            self._gen_array_read(expr)
            return
        if isinstance(expr, ast.BinaryOp):
            self._gen_binary(expr)
            return
        if isinstance(expr, ast.FuncCall):
            self._gen_funccall(expr)
            return
        raise CodeGenError(f"Expressão não suportada no codegen: '{expr}'")

    def _gen_array_read(self, expr: ast.ArrayAccess) -> None:
        """ Gera código para ler o valor de um array. """
        var_type = self._var_type(expr.name)
        if var_type == STRING:
            self._gen_char_value(expr)
            return
        assert isinstance(var_type, ast.ArrayType)
        self._gen_push_var(expr.name)
        self._gen_index_offset(expr.index, var_type.first)
        self.emit("LOADN")

    # mapeamento direto operador Pascal -> instrução da VM, para os operadores cuja geração de código é sempre igual
    _BINOP_INSTRUCTIONS = {
        "+": "ADD", "-": "SUB", "*": "MUL", "div": "DIV", "mod": "MOD",
        "and": "AND", "or": "OR",
        "<": "INF", "<=": "INFEQ", ">": "SUP", ">=": "SUPEQ",
    }

    def _gen_binary(self, expr: ast.BinaryOp) -> None:
        """ Gera código para uma operação binária.

        '=' e '<>' utiliza-se _gen_char_value invés da geração normal, para compara código ASCII (inteiros) em vez de strings.
        '<>' é implementado como EQUAL NOT

        Para os restantes operadores gera-se primeiro o operador esquerdo, depois o direito, e só no final a instrução.
        """
        op = expr.op

        if op in ("=", "<>"):
            if self._is_char_expr(expr.left) or self._is_char_expr(expr.right):
                self._gen_char_value(expr.left)
                self._gen_char_value(expr.right)
            else:
                self._gen_expr(expr.left)
                self._gen_expr(expr.right)
            self.emit("EQUAL")
            if op == "<>":
                self.emit("NOT")
            return

        instruction = self._BINOP_INSTRUCTIONS.get(op)
        if instruction is None:
            raise CodeGenError(f"Operador não suportado no codegen: '{op}'")
        self._gen_expr(expr.left)
        self._gen_expr(expr.right)
        self.emit(instruction)

    def _gen_funccall(self, call: ast.FuncCall) -> None:
        """ Gera código para uma chamada de função usada como expressão (ex: 'valor := BinToInt(bin)').

        'length' é a única função embutida nos exemplos do enunciado, mapeia-se diretamente para STRLEN, sem precisar da sequência
        CALL/RETURN (não é uma function definida pelo utilizador).

        Para as restantes (definidas pelo utilizador como function) segue a convenção PUSHI 0 + argumentos + PUSHA + CALL + POP.
        """
        if call.name == "length":
            self._gen_expr(call.args[0])
            self.emit("STRLEN")
            return

        self.emit("PUSHI 0")   # slot do valor de retorno
        for arg in call.args:
            self._gen_expr(arg)
        self.emit(f"PUSHA {call.name}")
        self.emit("CALL")
        if call.args:
            self.emit(f"POP {len(call.args)}")

    def _infer_type(self, expr: ast.Expression) -> ast.TypeSpec:
        """Inferencia de tipos minima, so para decidir WRITEI vs WRITES
        (reaproveita a logica ja usada no semantic_analyzer, mas
        implementada aqui para o codegen nao depender desse modulo)."""
        if isinstance(expr, ast.IntLiteral):
            return INTEGER
        if isinstance(expr, ast.BoolLiteral):
            return BOOLEAN
        if isinstance(expr, ast.StringLiteral):
            return STRING
        if isinstance(expr, ast.Variable):
            return self._var_type(expr.name)
        if isinstance(expr, ast.ArrayAccess):
            t = self._var_type(expr.name)
            if t == STRING:
                return INTEGER   # bin[i] -> codigo ASCII (int), ver _gen_char_value
            assert isinstance(t, ast.ArrayType)
            return t.element_type
        if isinstance(expr, ast.BinaryOp):
            if expr.op in ("and", "or", "=", "<>", "<", "<=", ">", ">="):
                return BOOLEAN
            return INTEGER
        if isinstance(expr, ast.FuncCall):
            if expr.name == "length":
                return INTEGER
            raise CodeGenError(f"Não sei inferir o tipo de retorno de '{expr.name}'")
        raise CodeGenError(f"Não sei inferir o tipo de: '{expr}'")


def generate_code(program: ast.Program) -> list[str]:
    """ Gera um código para o programa completo, devolvendo a lista de instruções. """
    return CodeGenerator().generate(program)