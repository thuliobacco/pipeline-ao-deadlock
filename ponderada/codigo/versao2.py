"""A4, versão 2: vazio=N, cheio=0 e mutex=1; ordem correta de aquisição.

Autor: Thúlio Sallum Bacco Pinto. Executar: python ponderada/codigo/versao2.py
O padrão realiza três execuções independentes de 20.000 amostras, N=5.
"""

from experimento import principal


if __name__ == "__main__":
    principal(2)

