from flask import Flask, render_template, request, Response
from datetime import datetime, timedelta
import os
from supabase import create_client, Client
from dotenv import load_dotenv
import csv
import io

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
bucket_name = "fotos_detecao"

# app.py está na raiz do projeto, ao lado de templates/ e static/,
# por isso o Flask encontra-as automaticamente sem precisarmos de
# calcular caminhos customizados.
app = Flask(__name__)


def obter_dados(data_filtro=None, data_inicio=None, data_fim=None, limitar=False):
    """
    Consulta a Supabase de 3 formas possíveis:
      1) Intervalo de datas (data_inicio e data_fim preenchidos)
      2) Dia único (data_filtro preenchido)
      3) Sem filtro (não deve acontecer, mas devolve vazio por segurança)

    Devolve (dados, total_real).
    """
    try:
        if data_inicio and data_fim:
            inicio_ts = f"{data_inicio} 00:00:00"
            fim_ts = f"{data_fim} 23:59:59"

            response = supabase.table("detecoes")\
                .select("*")\
                .gte("timestamp_inicio", inicio_ts)\
                .lte("timestamp_inicio", fim_ts)\
                .order("counter_dia", desc=True)\
                .execute()

            dados = response.data
            total_real = len(dados)

        elif data_filtro:
            response = supabase.table("detecoes")\
                .select("*")\
                .filter("timestamp_inicio", "ilike", f"{data_filtro}%")\
                .order("counter_dia", desc=True)\
                .execute()

            dados = response.data
            total_real = len(dados)

            if limitar:
                dados = dados[:20]

        else:
            dados, total_real = [], 0

    except Exception as e:
        print(f"Erro ao processar dados: {e}")
        dados, total_real = [], 0

    return dados, total_real


def obter_contexto_filtro():
    """
    Lê os parâmetros de filtro do pedido (dia único ou intervalo) e devolve
    tudo o que é preciso para consultar os dados e montar o pedido htmx
    da tabela (query string a usar em /tabela_atualizada).
    """
    data_filtro = request.args.get('data')
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    hoje_cpu = datetime.now().strftime('%Y-%m-%d')

    modo_intervalo = bool(data_inicio and data_fim)

    if modo_intervalo:
        dados, total_real = obter_dados(data_inicio=data_inicio, data_fim=data_fim)
        data_selecionada = data_filtro or hoje_cpu
        query_string = f"?data_inicio={data_inicio}&data_fim={data_fim}"
        rotulo_contagem = f"Contagem: {data_inicio} a {data_fim}"
    elif data_filtro:
        dados, total_real = obter_dados(data_filtro=data_filtro)
        data_selecionada = data_filtro
        query_string = f"?data={data_filtro}"
        rotulo_contagem = f"Contagem do Dia: {data_filtro}"
    else:
        dados, total_real = obter_dados(data_filtro=hoje_cpu, limitar=True)
        data_selecionada = hoje_cpu
        query_string = f"?data={hoje_cpu}"
        rotulo_contagem = f"Contagem do Dia: {hoje_cpu}"

    return {
        "dados": dados,
        "total_real": total_real,
        "data_selecionada": data_selecionada,
        "data_inicio": data_inicio or "",
        "data_fim": data_fim or "",
        "query_string": query_string,
        "rotulo_contagem": rotulo_contagem,
    }


@app.route('/', methods=['GET'])
def index():
    ctx = obter_contexto_filtro()

    return render_template('index.html',
                           detecoes=ctx["dados"],
                           data_selecionada=ctx["data_selecionada"],
                           data_inicio=ctx["data_inicio"],
                           data_fim=ctx["data_fim"],
                           query_string=ctx["query_string"],
                           rotulo_contagem=ctx["rotulo_contagem"],
                           total=ctx["total_real"])


@app.route('/tabela_atualizada', methods=['GET'])
def tabela_atualizada():
    ctx = obter_contexto_filtro()

    return render_template('tabela_parcial.html',
                           detecoes=ctx["dados"],
                           total=ctx["total_real"],
                           data_selecionada=ctx["data_selecionada"])
    
def obter_dados_paginados(data_inicio, data_fim, tamanho_pagina=1000):
    """
    Vai buscar TODOS os registos entre data_inicio e data_fim,
    contornando o limite de 1000 linhas do Supabase/PostgREST,
    fazendo pedidos sucessivos em blocos.
    """
    inicio_ts = f"{data_inicio} 00:00:00"
    fim_ts = f"{data_fim} 23:59:59"

    todos_dados = []
    pagina = 0

    while True:
        inicio_range = pagina * tamanho_pagina
        fim_range = inicio_range + tamanho_pagina - 1

        try:
            response = supabase.table("detecoes")\
                .select("*")\
                .gte("timestamp_inicio", inicio_ts)\
                .lte("timestamp_inicio", fim_ts)\
                .order("timestamp_inicio", desc=False)\
                .range(inicio_range, fim_range)\
                .execute()

            bloco = response.data

        except Exception as e:
            print(f"Erro ao processar dados (página {pagina}): {e}")
            break

        if not bloco:
            break

        todos_dados.extend(bloco)

        if len(bloco) < tamanho_pagina:
            # Já não há mais páginas a seguir
            break

        pagina += 1

    return todos_dados
    
@app.route('/exportar_csv', methods=['GET'])
def exportar_csv():
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')

    if not (data_inicio and data_fim):
        return "É necessário indicar data_inicio e data_fim.", 400

    dados = obter_dados_paginados(data_inicio, data_fim)

    contagem_por_dia = {}
    for registo in dados:
        dia = registo["timestamp_inicio"][:10]
        contagem_por_dia[dia] = contagem_por_dia.get(dia, 0) + 1

    # Gera todos os dias do intervalo e preenche com 0 os que não têm deteções
    data_inicio_dt = datetime.strptime(data_inicio, "%Y-%m-%d")
    data_fim_dt = datetime.strptime(data_fim, "%Y-%m-%d")

    linhas = []
    dia_atual = data_inicio_dt
    while dia_atual <= data_fim_dt:
        dia_str = dia_atual.strftime("%Y-%m-%d")
        if dia_str not in contagem_por_dia:
            contagem_por_dia[dia_str] = 0
        linhas.append((dia_str, contagem_por_dia[dia_str]))
        dia_atual += timedelta(days=1)

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=';')
    writer.writerow(["Data", "Numero de baldes"])
    for dia, contagem in linhas:
        writer.writerow([dia, contagem])

    nome_ficheiro = f"baldes_de_{data_inicio}_a_{data_fim}.csv"

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={nome_ficheiro}"}
    )


if __name__ == '__main__':
    app.run(debug=True)