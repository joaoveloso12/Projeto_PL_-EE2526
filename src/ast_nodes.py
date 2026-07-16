from dataclasses import dataclass
from typing import Union


# Base
class Node:
    """Classe-base de todos os nós da AST."""
    pass


# Tipos
class TypeSpec(Node):
    """Classe-base para especificações de tipo (integer, array, ...).
    Permite fazer isinstance(x, TypeSpec) na análise semântica para verificar se um nó representa um tipo válido.
    """
    pass

@dataclass(frozen=True)
class ScalarType(TypeSpec):
    """Tipo escalar simples: integer, string, boolean.
    frozen=True -> imutável e hash, útil para comparar tipos
    """
    name: str

@dataclass(frozen=True)
class ArrayType(TypeSpec):
    """Tipo array: array[first..last] of element_type
    (ex: array[1..5] of integer)
    """
    first: int
    last: int
    element_type: TypeSpec  # tipo dos elementos (ex: ScalarType("integer"))

    @property
    def size(self) -> int:
        """Número de elementos do array, útil na geração de código para reservar espaço em memória."""
        return self.last - self.first + 1


# Estrutura do programa
@dataclass
class VarDecl(Node):
    """Declaração de variável(is): var a, b, c : integer;"""
    names: list[str] # permite declarar várias variáveis do mesmo tipo numa só linha
    type_spec: TypeSpec

@dataclass
class Param(Node):
    """Parâmetro de uma função/procedimento."""
    names: list[str]
    type_spec: TypeSpec

@dataclass
class SubProgramDecl(Node):
    """Declaração de função ou procedimento.
    return_type is None  -> procedimento
    return_type not None -> função
    """
    name: str
    params: list[Param]
    return_type: TypeSpec | None
    block: "Block"  # corpo do subprograma (var locais + instruções)

@dataclass
class Block(Node):
    """Bloco: declarações de variáveis, subprogramas, e o corpo (compound).
    Usado tanto no Program principal como dentro de cada SubProgramDecl (cada função/procedimento tem o seu próprio Block).
    """
    declarations: list[VarDecl]
    subprograms: list[SubProgramDecl]
    compound: "Compound"  # o begin...end principal do bloco

@dataclass
class Program(Node):
    """Programa completo: program Nome; block."""
    name: str
    block: Block


# Instruções
class Statement(Node):
    """Class-base para instruções (tudo o que aparece dentro de um begin...end)."""
    pass

@dataclass
class Compound(Statement):
    """begin...end
    Agrupa uma sequência de instruções;
    É o corpo de um Block e também usado dentro de if/while/for quando há várias instruções.
    """
    statements: list[Statement]

@dataclass
class Assign(Statement):
    """target := value
    target só pode ser uma variável simples (Variable) ou uma posição de array (ArrayAccess)
    """
    target: Union["Variable", "ArrayAccess"]
    value: "Expression"

@dataclass
class ProcedureCall(Statement):
    """Chamada de procedimento como instrução: nome(args);
    Usado para writeln(...) e readln(...) nos exemplos.
    """
    name: str
    args: list["Expression"]    # writeln aceita múltiplos argumentos, separados por vírgulas

@dataclass
class If(Statement):
    """if condition then then_ [else else_]
    else_ é opcional (None por omissão)
    """
    condition: "Expression"
    then_: Statement
    else_: Statement | None = None

@dataclass
class While(Statement):
    """while condition do body"""
    condition: "Expression"
    body: Statement

@dataclass
class For(Statement):
    """for variable := start to/downto stop do body
    o booleano downto: distingue "to" (False, incrementa) de "downto" (True, decrementa)
    """
    variable: str
    start: "Expression"
    stop: "Expression"
    downto: bool
    body: Statement

@dataclass
class NoOp(Statement):
    """Instrução vazia. Permite "ignorar" uma instrução vazia sem rebentar o parser."""
    pass


# Expressões
class Expression(Node):
    """Classe-base para expressões."""
    pass

@dataclass
class IntLiteral(Expression):
    """Literal inteiro (ex: 5, 42, ...)."""
    value: int

@dataclass
class StringLiteral(Expression):
    """Literal string (ex: 'Ola, Mundo!')."""
    value: str

@dataclass
class BoolLiteral(Expression):
    """Literal booleano (ex: true, false)."""
    value: bool

@dataclass
class Variable(Expression):
    """Referência a uma variável simples (ex: n, fat, primo, ...)."""
    name: str

@dataclass
class ArrayAccess(Expression):
    """Acesso a uma posição de array (ex: números[i], bin[i], ...)."""
    name: str
    index: Expression   # apenas arrays de dimensão 1 (não há matrizes)

@dataclass
class BinaryOp(Expression):
    """Operação binária (ex: a + b, i <= n, num mod i, x and y, ...)."""
    left: Expression
    op: str   # guarda o operador como string (ex: "+", "mod", "and", "<=", ...) para simplificar o parser e a análise semântica
    right: Expression

@dataclass
class FuncCall(Expression):
    """Chamada de função usada como expressão: resultado := soma(a, b)"""
    name: str
    args: list[Expression]