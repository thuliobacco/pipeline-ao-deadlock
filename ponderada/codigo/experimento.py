"""A4: buffer circular de cinco posições, corrida e ordem de semáforos.

Autor: Thúlio Sallum Bacco Pinto. D1=6, D2=2, N=5.
Usa apenas a biblioteca padrão do Python 3. A carga padrão é de 20.000
amostras por execução, com três execuções independentes. O experimento
estressa a concorrência; ele não mede o prazo de 5 ms de um firmware.
"""

import argparse
import hashlib
import json
import platform
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


N = 5
TOTAL = 20_000
REPETICOES = 3
LIMITE_SEM_CONSUMO = 1.0
INTERVALO_MONITOR = 0.005
ATRASO_INICIAL_CONSUMIDOR = 0.002
INTERVALO_TROCA_PYTHON = 0.0001


def esperar(semaforo, parar):
    """Adquire semáforo, permitindo que o monitor encerre uma execução.

    Parâmetros: semaforo é um threading.Semaphore; parar é o Event de
    cancelamento. Retorna True se adquiriu, False se houve cancelamento.
    O timeout curto somente permite consultar parar: não trata uma espera
    de 20 ms como travamento nem altera a ordem de aquisição dos recursos.
    """
    while not parar.is_set():
        if semaforo.acquire(timeout=0.02):
            if parar.is_set():
                semaforo.release()
                return False
            return True
    return False


def executar(versao, total=TOTAL, tamanho=N):
    """Executa uma rodada e devolve métricas verificáveis por identidade.

    Parâmetros: versao é 1, 2 ou 3; total é a quantidade alvo de IDs
    consecutivos a partir de zero; tamanho é a capacidade do buffer.
    Retorna um dict com contagens, estados ao encerrar e duração.
    Inicia produtor, consumidor e monitor no chamador. Sem progresso de
    consumo por um segundo, solicita parada e aguarda ambas as threads.
    As leituras do monitor são diagnósticas, nunca controlam acesso ao
    buffer. O Event de parada não protege a região crítica da versão 1.
    """
    if versao not in (1, 2, 3) or total <= 0 or tamanho <= 0:
        raise ValueError("Versão deve ser 1, 2 ou 3; total e tamanho positivos.")

    buffer = [None] * tamanho
    ocupados = 0
    escrita = 0
    leitura = 0
    produzidas = 0
    recebidas = []
    parar = threading.Event()
    produtor_fim = threading.Event()
    consumidor_fim = threading.Event()
    vazio = threading.Semaphore(tamanho)
    cheio = threading.Semaphore(0)
    mutex = threading.Semaphore(1)
    inicio = time.monotonic()
    ultimo_consumo = inicio
    estados = {"produtor": "iniciando", "consumidor": "iniciando"}
    erros = []

    def produzir():
        """Produz IDs 0..total-1; não recebe parâmetros nem retorna valor.

        Acessa o estado fechado de executar. Na versão 1, separa leitura
        e escrita de ocupados por sleep(0). Nas demais, reserva vaga e
        mutex, invertendo somente essas duas aquisições na versão 3.
        Libera aquisições pendentes ao cancelar para permitir join real.
        """
        nonlocal ocupados, escrita, produzidas
        try:
            for amostra in range(total):
                if parar.is_set():
                    break
                if versao == 1:
                    estados["produtor"] = "espera ocupada: buffer cheio"
                    while ocupados >= tamanho and not parar.is_set():
                        pass
                    if parar.is_set():
                        break
                    estados["produtor"] = "escrita sem proteção"
                    buffer[escrita] = amostra
                    escrita = (escrita + 1) % tamanho
                    anterior = ocupados
                    time.sleep(0)
                    ocupados = anterior + 1
                    produzidas += 1
                    continue

                tem_mutex = False
                tem_vaga = False
                inseriu = False
                try:
                    if versao == 3:
                        estados["produtor"] = "espera mutex"
                        tem_mutex = esperar(mutex, parar)
                        if not tem_mutex:
                            break
                        estados["produtor"] = "espera vazio, retém mutex"
                        tem_vaga = esperar(vazio, parar)
                        if not tem_vaga:
                            break
                    else:
                        estados["produtor"] = "espera vazio"
                        tem_vaga = esperar(vazio, parar)
                        if not tem_vaga:
                            break
                        estados["produtor"] = "espera mutex"
                        tem_mutex = esperar(mutex, parar)
                        if not tem_mutex:
                            break
                    estados["produtor"] = "escrita com mutex"
                    buffer[escrita] = amostra
                    escrita = (escrita + 1) % tamanho
                    ocupados += 1
                    produzidas += 1
                    inseriu = True
                finally:
                    if tem_mutex:
                        mutex.release()
                    if inseriu:
                        cheio.release()
                    elif tem_vaga:
                        vazio.release()
            estados["produtor"] = "encerrado"
        except Exception as erro:
            erros.append("produtor: " + repr(erro))
            parar.set()
        finally:
            produtor_fim.set()

    def consumir():
        """Consome itens; não recebe parâmetros nem retorna valor.

        Aguarda 2 ms no início em todas as versões, simulando uma breve
        indisponibilidade do consumidor. Isso permite encher o buffer e
        exercitar a ordem de aquisição; não acrescenta travas ao algoritmo.
        Registra cada ID, inclusive repetições/valores inválidos. A lista
        de evidências tem um único escritor e não sincroniza o buffer.
        Na versão 1, drena até o produtor terminar e o contador indicar
        vazio, admitindo mais de total consumos se houver duplicações.
        Nas versões 2 e 3, encerra normalmente ao atingir total consumos.
        """
        nonlocal ocupados, leitura, ultimo_consumo
        try:
            estados["consumidor"] = "atraso inicial de 2 ms"
            time.sleep(ATRASO_INICIAL_CONSUMIDOR)
            while (versao == 1 or len(recebidas) < total) and not parar.is_set():
                if versao == 1:
                    estados["consumidor"] = "espera ocupada: buffer vazio"
                    while ocupados <= 0 and not parar.is_set():
                        if produtor_fim.is_set() and ocupados == 0:
                            break
                        pass
                    if parar.is_set() or (produtor_fim.is_set() and ocupados == 0):
                        break
                    estados["consumidor"] = "leitura sem proteção"
                    amostra = buffer[leitura]
                    leitura = (leitura + 1) % tamanho
                    anterior = ocupados
                    time.sleep(0)
                    ocupados = anterior - 1
                else:
                    tem_item = False
                    tem_mutex = False
                    retirou = False
                    try:
                        estados["consumidor"] = "espera cheio"
                        tem_item = esperar(cheio, parar)
                        if not tem_item:
                            break
                        estados["consumidor"] = "espera mutex, reservou cheio"
                        tem_mutex = esperar(mutex, parar)
                        if not tem_mutex:
                            break
                        estados["consumidor"] = "leitura com mutex"
                        amostra = buffer[leitura]
                        leitura = (leitura + 1) % tamanho
                        ocupados -= 1
                        retirou = True
                    finally:
                        if tem_mutex:
                            mutex.release()
                        if retirou:
                            vazio.release()
                        elif tem_item:
                            cheio.release()
                recebidas.append(amostra)
                ultimo_consumo = time.monotonic()
            estados["consumidor"] = "encerrado"
        except Exception as erro:
            erros.append("consumidor: " + repr(erro))
            parar.set()
        finally:
            consumidor_fim.set()

    produtor = threading.Thread(target=produzir, name="sensor")
    consumidor = threading.Thread(target=consumir, name="motor")
    produtor.start()
    consumidor.start()
    travou = False
    motivo = ("produtor encerrou e contador indicou buffer vazio" if versao == 1
              else "alvo de consumos alcançado")
    fotografia = None
    while not consumidor_fim.is_set() and not erros:
        if time.monotonic() - ultimo_consumo >= LIMITE_SEM_CONSUMO:
            travou = True
            motivo = "consumidor ficou pelo menos 1 s sem receber"
            fotografia = dict(estados)
            break
        time.sleep(INTERVALO_MONITOR)
    if erros:
        motivo = "exceção em uma thread"
    if fotografia is None:
        fotografia = dict(estados)
    ocupados_ao_parar = ocupados
    parar.set()
    produtor.join()
    consumidor.join()

    frequencias = Counter(x for x in recebidas if isinstance(x, int) and 0 <= x < total)
    validas = sum(frequencias.values())
    unicas = len(frequencias)
    duplicadas = sum(quantidade - 1 for quantidade in frequencias.values())
    fora_faixa = len(recebidas) - validas
    quebras_ordem = sum(atual != anterior + 1 for anterior, atual in zip(recebidas, recebidas[1:])
                       if isinstance(anterior, int) and isinstance(atual, int))
    return {
        "versao": versao,
        "n": tamanho,
        "alvo": total,
        "produzidas": produzidas,
        "consumidas": len(recebidas),
        "unicas_validas": unicas,
        "perdidas": total - unicas,
        "duplicadas": duplicadas,
        "fora_faixa": fora_faixa,
        "quebras_ordem": quebras_ordem,
        "travou": travou,
        "motivo": motivo,
        "ocupados_ao_parar": ocupados_ao_parar,
        "estados_ao_parar": fotografia,
        "threads_encerradas": not produtor.is_alive() and not consumidor.is_alive(),
        "erros": erros,
        "duracao_s": round(time.monotonic() - inicio, 6),
    }


def principal(versao):
    """Executa a interface de linha de comando para uma versão fixa.

    Parâmetro: versao é 1, 2 ou 3, informado pelo arquivo de entrada.
    Retorna None. Lê --amostras, --execucoes, --n e --formato para permitir
    reprodução e testes; sem opções usa os parâmetros oficiais do autor.
    Imprime tabela e diagnósticos ou JSON estruturado, sem gravar arquivos.
    """
    parser = argparse.ArgumentParser(description=f"A4, versão {versao}: produtor e consumidor")
    parser.add_argument("--amostras", type=int, default=TOTAL)
    parser.add_argument("--execucoes", type=int, default=REPETICOES)
    parser.add_argument("--n", type=int, default=N)
    parser.add_argument("--formato", choices=("texto", "json"), default="texto")
    args = parser.parse_args()
    if min(args.amostras, args.execucoes, args.n) <= 0:
        parser.error("amostras, execucoes e n devem ser positivos")
    resultados = []
    intervalo_anterior = sys.getswitchinterval()
    sys.setswitchinterval(INTERVALO_TROCA_PYTHON)
    try:
        for numero in range(1, args.execucoes + 1):
            resultado = executar(versao, args.amostras, args.n)
            resultado["execucao"] = numero
            resultados.append(resultado)
    finally:
        sys.setswitchinterval(intervalo_anterior)
    registro = {
        "autor": "Thúlio Sallum Bacco Pinto",
        "d1": 6,
        "d2": 2,
        "python": sys.version.split()[0],
        "sistema": platform.platform(),
        "fim_utc": datetime.now(timezone.utc).isoformat(),
        "sha256_experimento": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "limite_sem_consumo_s": LIMITE_SEM_CONSUMO,
        "atraso_inicial_consumidor_s": ATRASO_INICIAL_CONSUMIDOR,
        "intervalo_troca_python_s": INTERVALO_TROCA_PYTHON,
        "resultados": resultados,
    }
    if args.formato == "json":
        print(json.dumps(registro, ensure_ascii=False, indent=2))
        return
    print(f"A4 | versao {versao} | N={args.n} | alvo={args.amostras} | repeticoes={args.execucoes}")
    print(f"Python {registro['python']} | {registro['sistema']}")
    print("Carga: consumidor inicia 2 ms depois; timeout sem consumo = 1 s.")
    print("Intervalo de troca Python: 0,1 ms, igual nas tres versoes.")
    print("Exec | Produzidas | Consumidas | Perdidas | Duplicadas | Travou | Duracao(s)")
    for r in resultados:
        print(f"{r['execucao']:4} | {r['produzidas']:10} | {r['consumidas']:10} | "
              f"{r['perdidas']:8} | {r['duplicadas']:10} | "
              f"{'SIM' if r['travou'] else 'NAO':6} | {r['duracao_s']:.6f}")
        print(f"     unicas={r['unicas_validas']}; fora_faixa={r['fora_faixa']}; "
              f"quebras_ordem={r['quebras_ordem']}; ocupados={r['ocupados_ao_parar']}; "
              f"threads_encerradas={r['threads_encerradas']}")
        print(f"     produtor: {r['estados_ao_parar']['produtor']}; "
              f"consumidor: {r['estados_ao_parar']['consumidor']}")
        if r["erros"]:
            print("     erros:", "; ".join(r["erros"]))
    print("Perdidas = IDs alvo ausentes; duplicadas = ocorrencias validas alem da primeira.")
    print("Fim UTC:", registro["fim_utc"])
    print("SHA256 experimento.py:", registro["sha256_experimento"])

