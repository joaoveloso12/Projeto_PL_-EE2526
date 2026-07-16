import sys
import os
import argparse


def _encontrar_pasta_src():
    aqui = os.path.dirname(os.path.abspath(__file__))
    candidatos = [aqui] + [os.path.join(aqui, *([".."] * i), "src") for i in range(3)] \
                        + [os.path.join(aqui, "src")]
    for candidato in candidatos:
        if os.path.isfile(os.path.join(candidato, "lexer.py")):
            return candidato
    raise RuntimeError(
        "Não encontrei lexer.py nem em {0} nem numa pasta 'src' próxima. "
    )


sys.path.insert(0, _encontrar_pasta_src())

from lexer import lexer
from parser import parser
from semantic import SemanticAnalyzer
from semantic_errors import SemanticError
from codegen import generate_code, CodeGenError


def analise_lexica(codigo_fonte: str, mostrar_tokens: bool) -> None:
    """ Etapa 1: Análise Léxica.
    Percorre o código-fonte token a token, só para diagnóstico/contagem
    (o parser, na etapa 2, volta a percorrer o código do zero com o seu
    próprio lexer.input(), porque o PLY consome o gerador de tokens)."""
    print("=== 1. Análise Léxica ===")
    lexer.lineno = 1
    lexer.input(codigo_fonte)
    total = 0
    while True:
        tok = lexer.token()
        if not tok:
            break
        total += 1
        if mostrar_tokens:
            print(f"  {tok.type:<15} {tok.value!r}")
    print(f"{total} tokens reconhecidos.")
    print()


def analise_sintatica(codigo_fonte: str):
    """Etapa 2: Análise Sintática.
    Constrói a AST a partir do código-fonte. Termina o programa com
    uma mensagem clara se houver erro de sintaxe."""
    print("=== 2. Análise Sintática ===")
    lexer.lineno = 1
    ast_raiz = parser.parse(codigo_fonte, lexer=lexer)
    if ast_raiz is None:
        sys.exit(1)
    print(f"OK: programa '{ast_raiz.name}' reconhecido com sucesso.")
    print()
    return ast_raiz


def analise_semantica(ast_raiz) -> None:
    """Etapa 3: Análise Semântica.
    Verifica tipos, declarações de variáveis e coerência do código.
    Termina o programa com uma mensagem clara se houver erro semântico."""
    print("=== 3. Análise Semântica ===")
    try:
        SemanticAnalyzer().analyze(ast_raiz)
    except SemanticError as e:
        print(f"FALHOU: {e}")
        sys.exit(1)
    print("OK: nenhum erro semântico encontrado.")
    print()


def gerar_codigo(ast_raiz) -> list[str]:
    """Etapa 4: Geração de Código.
    Traduz a AST (já validada) para instruções da EWVM."""
    print("=== 4. Geração de Código ===")
    try:
        instrucoes = generate_code(ast_raiz)
    except CodeGenError as e:
        print(f"FALHOU: {e}")
        sys.exit(1)
    print(f"OK: {len(instrucoes)} instruções geradas.")
    print()
    return instrucoes


def compilar(codigo_fonte: str, mostrar_tokens: bool = False) -> list[str]:
    """Corre as 4 etapas do compilador, pela ordem do enunciado."""
    analise_lexica(codigo_fonte, mostrar_tokens)
    ast_raiz = analise_sintatica(codigo_fonte)
    analise_semantica(ast_raiz)
    return gerar_codigo(ast_raiz)


def main() -> None:
    parser_cli = argparse.ArgumentParser(description="Compilador Pascal -> EWVM")
    parser_cli.add_argument("ficheiro", help="ficheiro .pas de entrada")
    parser_cli.add_argument("-o", "--output", help="ficheiro .vm de saída (opcional)")
    parser_cli.add_argument("--tokens", action="store_true",
                             help="mostra os tokens reconhecidos na Análise Léxica")
    args = parser_cli.parse_args()

    with open(args.ficheiro, encoding="utf-8") as f:
        codigo_fonte = f.read()

    instrucoes = compilar(codigo_fonte, mostrar_tokens=args.tokens)

    caminho_saida = args.output or args.ficheiro.rsplit(".", 1)[0] + ".vm"
    with open(caminho_saida, "w", encoding="utf-8") as f:
        f.write("\n".join(instrucoes) + "\n")

    print(f"Código .vm escrito em: {caminho_saida}")


if __name__ == "__main__":
    main()