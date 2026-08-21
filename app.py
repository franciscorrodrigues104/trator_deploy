from flask import Flask, render_template, request
from datetime import datetime
import os
from supabase import create_client, Client
from dotenv import load_dotenv

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


if __name__ == '__main__':
    app.run(debug=True)