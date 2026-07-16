import ply.lex as lex

# palavras reservadas PASCAL
reserved = {
    'and' : 'AND',
    'array': 'ARRAY',
    'begin': 'BEGIN',
    'boolean': 'BOOLEAN_TYPE',
    'div': 'DIV',
    'downto': 'DOWNTO',
    'do': 'DO',
    'else': 'ELSE',
    'end': 'END',
    'false': 'FALSE',
    'for': 'FOR',
    'function': 'FUNCTION',
    'if': 'IF',
    'integer': 'INTEGER_TYPE',
    'mod': 'MOD',
    'not': 'NOT',
    'of': 'OF',
    'or': 'OR',
    'procedure': 'PROCEDURE',
    'program' : 'PROGRAM',
    'readln': 'READLN',
    'string': 'STRING_TYPE',
    'then': 'THEN',
    'to': 'TO',
    'true': 'TRUE',
    'var' : 'VAR',
    'while' : 'WHILE',
    'writeln': 'WRITELN',
}

tokens = [
    'ID',               # id
    'NUM_INT',          # integer
    'STRING_LITERAL',   # string
    'ASSIGN',           # assign ":="
    'RANGE',            # array range ".."
    'PLUS',             # plus "+"
    'MINUS',            # minus "-"
    'TIMES',            # times "*"
    'EQ',               # equal "="
    'LE',               # less or equal "<="
    'GE',               # greater or equal ">="
    'LT',               # less than "<"
    'GT',               # greater than ">"
    'NE',                # not equal "<>"
    'SEMI',             # semi ";"
    'COLON',            # colon ":"
    'COMMA',            # comma ","
    'LPAREN',           # left parentheses "("
    'RPAREN',           # right parentheses ")"
    'LBRACKET',         # left square bracket "["
    'RBRACKET',         # right square bracket "]"
    'DOT',              # dot "."
] + list(reserved.values())

t_ASSIGN = r':='
t_RANGE = r'\.\.'
t_PLUS = r'\+'
t_MINUS = r'-'
t_TIMES = r'\*'
t_EQ = r'='
t_LE = r'<='
t_GE = r'>='
t_LT = r'<'
t_GT = r'>'
t_NE = r'<>'
t_SEMI = r';'
t_COLON = r':'
t_COMMA = r','
t_LPAREN = r'\('
t_RPAREN = r'\)'
t_LBRACKET = r'\['
t_RBRACKET = r'\]'
t_DOT = r'\.'

t_ignore = ' \t'    # ignora espaços e tabs

# define 3 tipos de comentários
def t_COMMENT(t):
    r"\{[^}]*\}|\(\*(.|\n)*?\*\)|//.*"

    # 1- \{[^}]*\} -> { comentário }
    #       \{ - chaveta abertura
    #       [^}]* - qualquer sequência de caracteres, exceto '}' (0 ou mais vezes)
    #       \} - chaveta fecho
    # 2- \(\*(.|\n)*?\*\) -> (* comentário \n continua *)
    #       \(\* - abertura do comentário
    #       (.|\n)*? - qualquer carácter ou mudança de linha, até encontrar o primeiro fecho de comentário
    #       \*\) - fecho do comentário
    # 3- //.* -> // comentário
    #       // - duas barras
    #       .* - qualquer carácter nessa linha
    t.lexer.lineno += t.value.count('\n')
    # incrementa número de linhas contadas

# define IDs
def t_ID(t):
    r"[a-zA-Z_][a-zA-Z0-9_]*"
    # [a-zA-Z_] -> primeiro carácter tem de ser letra (minúscula ou maiúscula) ou um underscore
    # [a-zA-Z0-9_]* -> os caracteres seguintes (zero ou mais) têm de ser letras (minúsculas ou maiúsculas) ou dígitos ou underscores
    t.type = reserved.get(t.value.lower(), 'ID')
    # define o tipo do token correspondente (se não existir, define tipo ID)
    return t

# define inteiros
def t_NUM_INT(t):
    r'\d+'
    # \d+ -> qualquer dígito (1 ou mais)
    t.value = int(t.value)
    return t

# define strings
def t_STRING_LITERAL(t):
    r"'([^']|'')*'"
    # ' -> plica inicial
    # ([^']|'')* -> qualquer carácter que não seja uma plica, ou duas plicas seguidas (0 ou mais vezes)
    # ' -> plica final
    t.value = t.value[1:-1].replace("''", "'")
    # remove a plica inicial e a final, e caso haja 2 plicas seguidas, substitui por apenas uma
    return t

# define mudanças de linha
def t_newline(t):
    r'\n+'
    # \n+ -> mudança de linha (1 ou mais)
    t.lexer.lineno += len(t.value)

# define erro (caracteres inválidos)
def t_error(t):
    print(f"Carácter inesperado '{t.value[0]}' na linha {t.lineno}.")
    # imprime o carácter que causou erro, e a linha correspondente
    t.lexer.skip(1)
    # ignora o carácter inesperado e continua a tentar tokenizar a partir do próximo

# compila e devolve o objeto lexer
lexer = lex.lex()