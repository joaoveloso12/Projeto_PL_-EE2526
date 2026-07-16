import ply.yacc as yacc

from lexer import tokens, lexer
import ast_nodes as ast

# Precedência de operadores (do menos para o mais prioritário).
precedence = (
    ('nonassoc', 'IFX'),    # proíbe encadear
    ('nonassoc', 'ELSE'),   # proíbe encadear
    ('left', 'OR'),         # reduce - fecha o grupo à esquerda primeiro
    ('left', 'AND'),        # reduce - fecha o grupo à esquerda primeiro
    ('nonassoc', 'EQ', 'NE', 'LT', 'GT', 'LE', 'GE'),   # proíbe encadear
    ('left', 'PLUS', 'MINUS'),          # reduce - fecha o grupo à esquerda primeiro
    ('left', 'TIMES', 'DIV', 'MOD'),    # reduce - fecha o grupo à esquerda primeiro
)

# Programa / Bloco
def p_programa(p):
    """program : PROGRAM ID SEMI block DOT"""
    # Nó raiz da AST. Ex: "program HelloWorld; ... ." -> Program(name="HelloWorld", block=...)
    p[0] = ast.Program(name=p[2], block=p[4])

def p_block(p):
    """block : subprogram_decls declarations compound_statement"""
    # um "block" é reutilizado tanto no programa principal como dentro de cada function (cada uma tem o seu próprio bloco de declarações)
    # subprogram_decls vem ANTES de declarations na gramática porque o Exemplo 5 do enunciado declara a function ANTES do "var" do programa principal
    # nos outros exemplos (sem subprogramas) não faz diferença, porque subprogram_decls fica vazio ([]).
    p[0] = ast.Block(declarations=p[2], subprograms=p[1], compound=p[3])


# Declarações de variáveis
def p_declarations(p):
    """declarations : VAR var_declarations_list
                    | empty """
    # se não houver nenhum "var" no bloco (Exemplo 1), cai na alternativa "empty" e devolve uma lista vazia
    p[0] = p[2] if len(p) == 3 else []

def p_var_declarations_list(p):
    """var_declarations_list : var_declarations_list var_declarations
                             | var_declarations """
    p[0] = p[1] + [p[2]] if len(p) == 3 else [p[1]]

def p_var_declarations(p):
    """var_declarations : id_list COLON type_spec SEMI"""
    # id_list trata da possibilidade de várias variáveis com o mesmo tipo numa única linha
    p[0] = ast.VarDecl(names=p[1], type_spec=p[3])

def p_id_list(p):
    """id_list : id_list COMMA ID
               | ID """
    # lista de nomes separados por vírgula: "n, i, fat" -> ['n', 'i', 'fat']
    p[0] = p[1] + [p[3]] if len(p) == 4 else [p[1]]

def p_type_spec_scalar(p):
    """type_spec : INTEGER_TYPE
                 | STRING_TYPE
                 | BOOLEAN_TYPE """
    # normaliza-se para minúsculas para que o nome do ScalarType seja sempre consistente
    p[0] = ast.ScalarType(name=p[1].lower())

def p_type_spec_array(p):
    """type_spec : ARRAY LBRACKET NUM_INT RANGE NUM_INT RBRACKET OF type_spec"""
    # Ex: "array[1..5] of integer" -> ArrayType(first=1, last=5, element_type=ScalarType("integer"))
    # element_type é ele próprio um type_spec, o que permite arrays de arrays, embora os exemplos do enunciado só usem arrays de escalares.
    p[0] = ast.ArrayType(first=p[3], last=p[5], element_type=p[8])


# SubProgramas (funções)
def p_subprogram_decls(p):
    """subprogram_decls : subprogram_decls subprogram_decl
                        | empty """
    p[0] = p[1] + [p[2]] if len(p) == 3 else []

def p_subprogram_decl_function(p):
    """subprogram_decl : FUNCTION ID LPAREN params RPAREN COLON type_spec SEMI block SEMI"""
    # Ex: "function BinToInt(bin: string): integer; <bloco> ;"
    # o corpo da função (p[9]) é ele próprio um "block" completo, com as suas próprias declarações locais e instrução composta.
    p[0] = ast.SubProgramDecl(name=p[2], params=p[4], return_type=p[7], block=p[9])

def p_params(p):
    """params : params_list
              | empty """
    # permite funções sem parâmetros
    p[0] = p[1] if p[1] is not None else []

def p_params_list(p):
    """params_list : params_list SEMI param
                   | param """
    # vários parâmetros separam-se por ";" em Pascal
    p[0] = p[1] + [p[3]] if len(p) == 4 else [p[1]]

def p_param(p):
    """param : id_list COLON type_spec"""
    p[0] = ast.Param(names=p[1], type_spec=p[3])


# Instruções
def p_compound_statement(p):
    """compound_statement : BEGIN statement_list END"""
    # begin ... end
    p[0] = ast.Compound(statements=p[2])

def p_statement_list(p):
    """statement_list : statement_list SEMI statement
                      | statement"""
    # como "statement" pode reduzir a partir de "empty", um ";" a mais antes do "end" (ex: "writeln(...);\nend."),
    # produz um NoOp extra no fim da lista, representando uma instrução vazia, invés de bug
    p[0] = p[1] + [p[3]] if len(p) == 4 else [p[1]]

def p_statement(p):
    """statement : compound_statement
                 | assign_statement
                 | if_statement
                 | while_statement
                 | for_statement
                 | procedure_call_statement
                 | empty """
    p[0] = p[1] if p[1] is not None else ast.NoOp()

def p_assign_statement(p):
    """assign_statement : variable ASSIGN expression"""
    # target := value
    p[0] = ast.Assign(target=p[1], value=p[3])

def p_variable_simple(p):
    """variable : ID"""
    p[0] = ast.Variable(name=p[1])

def p_variable_array(p):
    """variable : ID LBRACKET expression RBRACKET"""
    # Ex: "numeros[i]" -> ArrayAccess(name="numeros", index=Variable("i"))
    # só suporta um índice (arrays de dimensão 1), suficiente para os exemplos.
    p[0] = ast.ArrayAccess(name=p[1], index=p[3])

def p_if_statement(p):
    """if_statement : IF expression THEN statement %prec IFX
                    | IF expression THEN statement ELSE statement """
    # O "%prec IFX" na primeira alternativa (sem ELSE) é o que resolve o dangling-else, em conjunto com a tabela "precedence" no topo
    # do ficheiro; dá a esta regra uma precedência mais baixa do que ELSE, fazendo o parser preferir continuar a ler um "else" que apareça
    # a seguir (shift), em vez de fechar este if sem else primeiro (reduce).
    # O else associa-se sempre ao if mais próximo!
    if len(p) == 5:
        p[0] = ast.If(condition=p[2], then_=p[4])
    else:
        p[0] = ast.If(condition=p[2], then_=p[4], else_=p[6])

def p_while_statement(p):
    """while_statement : WHILE expression DO statement"""
    p[0] = ast.While(condition=p[2], body=p[4])

def p_for_statement(p):
    """for_statement : FOR ID ASSIGN expression TO expression DO statement"""
    # for i := start to stop do body (incrementa)
    p[0] = ast.For(variable=p[2], start=p[4], stop=p[6], downto=False, body=p[8])

def p_for_statement_downto(p):
    """for_statement : FOR ID ASSIGN expression DOWNTO expression DO statement"""
    # for i := start downto stop do body (decrementa - Exemplo 5)
    p[0] = ast.For(variable=p[2], start=p[4], stop=p[6], downto=True, body=p[8])

def p_procedure_call_writeln(p):
    """procedure_call_statement : WRITELN LPAREN expression_list RPAREN"""
    p[0] = ast.ProcedureCall(name="writeln", args=p[3])

def p_procedure_call_readln(p):
    """procedure_call_statement : READLN LPAREN expression_list RPAREN"""
    p[0] = ast.ProcedureCall(name="readln", args=p[3])

def p_expression_list(p):
    """expression_list : expression_list COMMA expression
                       | expression """
    p[0] = p[1] + [p[3]] if len(p) == 4 else [p[1]]


# Expressões
def p_expression_binp(p):
    """expression : expression PLUS expression
                  | expression MINUS expression
                  | expression TIMES expression
                  | expression DIV expression
                  | expression MOD expression
                  | expression AND expression
                  | expression OR expression
                  | expression EQ expression
                  | expression LE expression
                  | expression GE expression
                  | expression LT expression
                  | expression GT expression
                  | expression NE expression """
    p[0] = ast.BinaryOp(left=p[1], op=p[2], right=p[3])

def p_expression_group(p):
    """expression : LPAREN expression RPAREN"""
    # Parênteses só servem para forçar a ordem de avaliação; não criam nenhum nó extra na AST
    p[0] = p[2]

def p_expression_num(p):
    """expression : NUM_INT"""
    p[0] = ast.IntLiteral(value=p[1])

def p_expression_string(p):
    """expression : STRING_LITERAL"""
    p[0] = ast.StringLiteral(value=p[1])

def p_expression_true(p):
    """expression : TRUE"""
    p[0] = ast.BoolLiteral(value=True)

def p_expression_false(p):
    """expression : FALSE"""
    p[0] = ast.BoolLiteral(value=False)

def p_expression_variable(p):
    """expression : variable"""
    # reaproveita a regra "variable"(ID simples ou array[índice]) para poder ser usada numa expressão maior, (ex: "soma + numeros[i]").
    p[0] = p[1]

def p_expression_funccall(p):
    """expression : ID LPAREN expression_list RPAREN"""
    p[0] = ast.FuncCall(name=p[1], args=p[3])


# Regra vazia (utilizada em declarations/subprogram_decls/statement)
def p_empty(p):
    """empty : """
    pass

def p_error(p):
    """ Chamada automaticamente pelo PLY sempre que o parser encontra um token inválido.
    O yacc.yacc() já trata de fazer parser.parse(...) e devolver None nestes casos, sem lançar exceção.
    """
    if p:
        print(f"Erro de sintaxe '{p.value}' na linha {p.lineno}")
    else:
        print("Erro de sintaxe: fim de ficheiro inesperado")

# constrói a gramática, e devolve um objeto parser
parser = yacc.yacc()