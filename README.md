# Tato: do pipeline ao deadlock

Thúlio Sallum Bacco Pinto

Análise de arquitetura, concorrência e decisão de produção de uma pulseira sensorial com prazo de processamento de 5 ms.

A atividade está em [ponderada/ponderada-tato.md](ponderada/ponderada-tato.md). Os parâmetros individuais são D1 = 6, D2 = 2 e N = 5.

## Executar a questão A4

Requisito: Python 3.10 ou superior, sem bibliotecas externas. Abra o PowerShell ou um terminal na raiz deste repositório. Cada comando executa a versão indicada três vezes, com 20.000 amostras por execução:

```powershell
python ponderada/codigo/versao1.py
```

```powershell
python ponderada/codigo/versao2.py
```

```powershell
python ponderada/codigo/versao3.py
```

Em Linux ou macOS, substitua `python` por `python3`, se necessário. Os resultados aparecem na saída padrão; os programas não alteram arquivos nem acessam rede ou dispositivos da pulseira.

A versão 1 contém a corrida exigida pelo exercício e a versão 3 contém a ordem de aquisição que permite deadlock. O monitor encerra a execução quando o consumidor passa um segundo sem receber uma amostra. A versão 2 usa os três semáforos na ordem correta. Os números das versões defeituosas dependem do escalonamento e podem mudar entre execuções.

Os experimentos exercitam sincronização em um computador de desenvolvimento. Não medem o prazo de 5 ms no hardware da pulseira.
