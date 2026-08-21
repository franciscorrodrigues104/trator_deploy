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


@app.route('/', methods=['GET'])
def index():
    data_filtro = request.args.get('data')
    hoje_cpu = datetime.now().strftime('%Y-%m-%d')

    try:
        query = supabase.table("detecoes").select("*")

        if data_filtro:
            response = query.filter("timestamp_inicio", "ilike", f"{data_filtro}%")\
                            .order("counter_dia", desc=True).execute()
            dados = response.data
            total_real = len(dados)
        else:
            response = query.filter("timestamp_inicio", "ilike", f"{hoje_cpu}%")\
                            .order("counter_dia", desc=True).execute()
            dados = response.data
            total_real = len(dados)

            dados = dados[:20]

    except Exception as e:
        print(f"Erro ao processar dados: {e}")
        dados = []
        total_real = 0

    return render_template('index.html',
                           detecoes=dados,
                           data_selecionada=data_filtro or hoje_cpu,
                           total=total_real)


@app.route('/tabela_atualizada', methods=['GET'])
def tabela_atualizada():
    data_filtro = request.args.get('data')
    hoje_cpu = datetime.now().strftime('%Y-%m-%d')
    alvo = data_filtro if data_filtro else hoje_cpu

    try:
        response = supabase.table("detecoes")\
            .select("*")\
            .filter("timestamp_inicio", "ilike", f"{alvo}%")\
            .order("counter_dia", desc=True).execute()

        dados = response.data
        total_real = len(dados)
        exibir_dados = dados
    except Exception as e:
        print(f"Erro ao processar dados: {e}")
        exibir_dados, total_real = [], 0

    return render_template('tabela_parcial.html', detecoes=exibir_dados, total=total_real, data_selecionada=alvo)


if __name__ == '__main__':
    app.run(debug=True)