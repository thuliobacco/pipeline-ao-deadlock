"""A4, versão 3: produtor adquire mutex antes de vazio, permitindo deadlock.

Autor: Thúlio Sallum Bacco Pinto. Executar: python ponderada/codigo/versao3.py
O padrão realiza três execuções independentes de 20.000 amostras, N=5.
"""

from experimento import principal


if __name__ == "__main__":
    principal(3)
