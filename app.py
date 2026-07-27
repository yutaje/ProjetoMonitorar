from fileinput import filename
import os
from flask import Flask , jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime
import json
from apscheduler.schedulers.background import BackgroundScheduler
from flask_jwt_extended import JWTManager, create_access_token
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
from flask_jwt_extended import jwt_required, get_jwt_identity




PASTA_BACKUPS = 'backups_diarios'
os.makedirs(PASTA_BACKUPS, exist_ok=True)


#criar API
app = Flask(__name__)
CORS(app)


app.config["JWT_SECRET_KEY"] = "chave_ty_xi"

jwt = JWTManager(app)


app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:root@localhost/teste_monitor'

#desligar avisos flask
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


class Projeto(db.Model):
    __tablename__ = 'projeto'

    id = db.Column(db.Integer, primary_key=True)

    nome = db.Column(db.String(150), unique=True, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome
    }


class Caminho(db.Model):
    __tablename__ = 'caminho'

    id = db.Column(db.Integer, primary_key=True)

    localizacao = db.Column(db.String(500),nullable=False)

    projeto_id = db.Column(db.Integer, db.ForeignKey('projeto.id'), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'localizacao': self.localizacao,
            'projeto_id': self.projeto_id
        }


class Historico(db.Model):
    __tablename__ = 'historico'

    id = db.Column(db.Integer, primary_key=True)

    caminho_id = db.Column(db.Integer, db.ForeignKey('caminho.id'), nullable=False)

    data_verificacao = db.Column(db.DateTime, default=db.func.now(), nullable=False)

    estado = db.Column(db.String(50), nullable=False)

    detalhes = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'data_verificacao': str(self.data_verificacao),
            'caminho_id': self.caminho_id,
            'estado': self.estado,
            'detalhes': self.detalhes
        }


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    #guardar a passe encriptada
    password = db.Column(db.String(200), nullable=False)

    def to_dict(self):
        return{
            "id": self.id,
            "username": self.username
        }



#construir
with app.app_context():
    db.create_all()


#1 rota
@app.route('/')
def pagina_principal():
    return 'funcional'


#rota para listar todos os users
@app.route('/users')
def listar_users():
        todos_users = db.session.execute(db.select(Utilizador)).scalars().all()

        lista = []

    #percorrer users que vieram da bd
        for user in todos_users:
            lista.append({
                'id': user.id,
                'nome': user.nome,
                'email': user.email
            })

        return jsonify(lista)


#rota para criar novo projeto
@app.route('/projetos', methods=['POST'])
def criar_projeto():
    dados = request.get_json()

    #verifica se enviaram os dados e se o nome existe no JSON
    if not dados or 'nome' not in dados:
        return jsonify({"erro": "Falta o campo 'nome' no pedido JSON."}), 400

    #limpa espaços e verifica senao esta vazio
    nome_limpo = dados['nome'].strip()
    if not nome_limpo:
        return jsonify({"erro": "O nome do projeto não pode estar vazio."}), 400

    #cria o proj na memoria
    novo_projeto = Projeto(nome=nome_limpo,)
    
#grava na bd
    db.session.add(novo_projeto)
    db.session.commit()

    return jsonify(novo_projeto.to_dict()), 201


#rota para listar os projs
@app.route('/projetos', methods=['GET'])
def listar_projetos():
    todos_projetos = Projeto.query.all()
    resultado = [projeto.to_dict() for projeto in todos_projetos]

    return jsonify(resultado), 200


#rota para apagar um proj
@app.route('/projetos/<int:projeto_id>', methods=['DELETE'])
def apagar_projeto(projeto_id):
    #procura proj pelo ID senao existe da erro
    projeto = Projeto.query.get_or_404(projeto_id)

    #vai buscar todos os caminhos associados ao proj
    caminhos_associados = Caminho.query.filter_by(projeto_id=projeto.id).all()

    #para cada caminho, aoaga o historico primeiro
    for caminho in caminhos_associados:
        Historico.query.filter_by(caminho_id=caminho.id).delete()

    #apaga os proprios caminhos associados ao proj
    Caminho.query.filter_by(projeto_id=projeto.id).delete()

    #apaga o proj original
    db.session.delete(projeto)

    #grava na bd
    db.session.commit()

    #devolve resposta de sucesso
    return jsonify({
        "mensagem": f"O projeto '{projeto.nome}' e todos os seus registos foram apagados com sucesso!"
    }), 200


#rota para editar um proj
@app.route('/projetos/<int:id>', methods=['PUT'])
def editar_projeto(id):
    #procura o proj na bd
    projeto = Projeto.query.get(id)
    if not projeto:
        return jsonify({"erro": "Projeto não encontrado."}), 404

    dados = request.get_json()

    #validaçao
    if not dados or 'nome' not in dados:
        return jsonify({"erro": "Falta o campo 'nome' no pedido JSON."}), 400

    nome_limpo = dados['nome'].strip()
    if not nome_limpo:
        return jsonify({"erro": "O nome do projeto não pode estar vazio."}), 400

    #atualiza o nome e grava na bd
    projeto.nome = nome_limpo
    db.session.commit()

    return jsonify(projeto.to_dict()), 200


#rota para apagar um caminho individual
@app.route('/caminhos/<int:caminho_id>', methods=['DELETE'])
def apagar_caminho(caminho_id):
    #procura o caminho pelo ID
    caminho = Caminho.query.get_or_404(caminho_id)

    #apaga o historico associado a pasta
    Historico.query.filter_by(caminho_id=caminho.id).delete()

    #apaga o caminho
    db.session.delete(caminho)

    #grava na bd
    db.session.commit()

    return jsonify({
        "mensagem": f"O caminho '{caminho.localizacao}' e o seu histórico foram apagados com sucesso!"
    }), 200


#rota para editar um caminho individual
@app.route('/caminhos/<int:id>', methods=['PUT'])
def editar_caminho(id):
    #prcura caminho pelo ID
    caminho = Caminho.query.get(id)

    #senao existe devolve erro
    if not caminho:
        return jsonify({"erro": "Caminho não encontrado."}), 404

    dados = request.get_json()

    nova_localizacao = dados.get('localizacao', '').strip()

    #validar se a localizacao nao ficou vazio
    if not nova_localizacao:
        return jsonify({"erro": "A localização do caminho é obrigatória e não pode estar vazio!"}), 400

    #atualiza a bd com a nova localizacao
    caminho.localizacao = nova_localizacao
    db.session.commit()

    #devolve a confirmaçao
    return jsonify({
        "mensagem": "Caminho atualizado com sucesso!",
        "caminho_editado": caminho.to_dict()     
    }), 200


#rota para associar um novo caminho a um projeto
@app.route('/projetos/<int:projeto_id>/caminhos', methods=['POST'])
def criar_caminho(projeto_id):
    #verificar se o proj existe na bd
    projeto = Projeto.query.get_or_404(projeto_id)

    dados = request.get_json()

    #criar caminho ligando o ao id do proj 
    novo_caminho = Caminho(
        localizacao=dados['localizacao'],
        projeto_id=projeto.id
    )

    db.session.add(novo_caminho)
    db.session.commit()

    return jsonify({
        "mensagem": "Caminho associado com sucesso",
        "caminho": {
            "id": novo_caminho.id,
            "localizacao": novo_caminho.localizacao,
            "projeto_id": novo_caminho.projeto_id
        }
    }), 201


@app.route('/caminhos/<int:caminho_id>/verificar', methods=['POST'])
def verificar_caminho(caminho_id):
    #vai buscar o caminho a bd, se nao existir devolve 404
    caminho_obj = Caminho.query.get_or_404(caminho_id)

    #verifica se a pasta existe
    pasta_existe = os.path.exists(caminho_obj.localizacao)

    if pasta_existe:
        estado_atual = 'OK'
        detalhes_msg = 'A pasta existe e está acessível.'
    else:
        estado_atual = 'ERRO'
        detalhes_msg = 'Alerta: A pasta não foi encontrada ou o caminho é inválido.'

    #cria novo registo na tabela historico
    novo_historico = Historico(
        caminho_id=caminho_obj.id,
        estado=estado_atual,
        detalhes=detalhes_msg
    )

    db.session.add(novo_historico)
    db.session.commit()

    #devolve o resultado em JSON
    return jsonify({
        "mensagem": "Verificação concluída",
        "caminho_id": caminho_obj.id,
        "localizacao": caminho_obj.localizacao,
        "estado": estado_atual,
        "detalhes": detalhes_msg,
        "data_verificacao": str(novo_historico.data_verificacao)
    }), 201

#rota para listar caminhos de um proj
@app.route('/projetos/<int:projeto_id>/caminhos', methods=['GET'])
def listar_caminhos_projeto(projeto_id):

    projeto = Projeto.query.get_or_404(projeto_id)
    caminhos = Caminho.query.filter_by(projeto_id=projeto.id).all()

    resultado = [{
        'id': c.id,
        'localizacao': c.localizacao,
        'projeto_id': c.projeto_id
    } for c in caminhos]

    return jsonify(resultado), 200

#rota para consultar o historico de um caminho
@app.route('/caminhos/<int:caminho_id>/historico', methods=['GET'])
def ver_historico_caminho(caminho_id):
    #verifica se o caminho existe
    caminho = Caminho.query.get_or_404(caminho_id)

    #vai buscar todos os registos historicos associados ao caminho
    registos = Historico.query.filter_by(caminho_id=caminho.id).order_by(Historico.data_verificacao.desc()).all()

    #converte os registos para JSON
    resultado = [{
        "id": h.id,
        "estado": h.estado,
        "detalhes": h.detalhes,
        "data_verificacao": str(h.data_verificacao)
    } for h in registos]

    return jsonify(resultado), 200


#rota para stats
@app.route('/estatisticas', methods=['GET'])
def obter_estatisticas():
    #conta quantos registos existem em cada tabela
    total_projetos = Projeto.query.count()
    total_caminhos = Caminho.query.count()
    total_verificacoes = Historico.query.count()

    #prep do relatorio final em JSON
    relatorio = {
        "dashboard": {
            "projetos_ativos": total_projetos,
            "caminhos_monitorizados": total_caminhos,
            "verificacoes_realizadas": total_verificacoes
        }
    }

    return jsonify(relatorio), 200

#rota para o indice
@app.route('/api/backups', methods=['GET'])
def listar_backups():
    try:
        #lista todos os ficheiros da pasta que sao JSON
        ficheiros = [f for f in os.listdir(PASTA_BACKUPS) if f.endswith('.json')]

        #ordena do mais antigo para o mais recente
        ficheiros.sort(reverse=True)

        #devolve a lista em JSON
        return jsonify({
            "sucesso": True, 
            "backups": ficheiros
        }), 200

    except Exception as e:
        #se algo correr mal devolve erro
        return jsonify({
            "sucesso": False, 
            "erro": f"Erro ao listar backups: {str(e)}"
        }), 500


@app.route('/api/backups/<filename>', methods=['GET'])
def ler_backup(filename):
    try:
        #limpa o nome do ficheiro para segurança
        nome_seguro = secure_filename(filename)
        caminho_ficheiro = os.path.join(PASTA_BACKUPS, nome_seguro)

        #verifica se o ficheiro existe na pasta
        if not os.path.exists(caminho_ficheiro):
            return jsonify({
                "sucesso": False, 
                "erro": "Backup não encontrado."
            }), 404

        #abre o ficheiro le o que esta dentro e transforma de volta em JSON
        with open(caminho_ficheiro, 'r', encoding='utf-8') as f:
            dados_backup = json.load(f)

        #devolve dados ao frontend
        return jsonify({
            "sucesso": True,
            "dados": dados_backup
        }), 200
        
    except Exception as e:
        return jsonify({
            "sucesso": False, 
            "erro": f"Erro ao ler o ficheiro: {str(e)}"
        }), 500


#rota para gerar backup com os dados da bd
@app.route('/api/backups/gerar', methods=['POST'])
def criar_backup_manual():
    try:
        #vai a bd buscar tudo
        caminhos = Caminho.query.all()
        projetos = Projeto.query.all()

        #prepara os dados
        dados_para_guardar = {
            "data_backup": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "caminhos": [c.to_dict() for c in caminhos],
            "projetos": [p.to_dict() for p in projetos]
        }

        #gera nome do ficheiro com timestamp
        # 3. Cria o nome só com ano_mes_dia_hora_minuto
        data_str = datetime.now().strftime("%Y_%m_%d-%Hh%M")
        nome_ficheiro = f"backup_{data_str}.json"
        caminho_completo = os.path.join(PASTA_BACKUPS, nome_ficheiro)

        #escreve dados no ficheiro JSON
        with open(caminho_completo, 'w', encoding='utf-8') as f:
            json.dump(dados_para_guardar, f, ensure_ascii=False, indent=4)

        return jsonify({
            "sucesso": True, 
            "mensagem": f"Backup {nome_ficheiro} criado com sucesso!",
            "ficheiro": nome_ficheiro
        }), 201

    except Exception as e:
        return jsonify({
            "sucesso": False, 
            "erro": f"Erro ao gerar o backup: {str(e)}"
        }), 500


#func que o robo vai executar solo
def gerar_backup_automatico():
    #key para aceder a bd
    with app.app_context():
        caminhos = Caminho.query.all()
        projetos = Projeto.query.all()

        dados = {
            "data_backup": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "caminhos": [c.to_dict() for c in caminhos],
            "projetos": [p.to_dict() for p in projetos]
        }

        #gera nome do ficheiro com timestamp
        data_str = datetime.now().strftime("%Y_%m_%d-%Hh%M")
        nome_ficheiro = f"backup_auto_{data_str}.json" # Adicionei 'auto' para distinguir
        caminho_completo = os.path.join(PASTA_BACKUPS, nome_ficheiro)

        with open(caminho_completo, 'w', encoding='utf-8') as f:
            json.dump(dados, f, ensure_ascii=False, indent=4)

        return nome_ficheiro


scheduler = BackgroundScheduler()

# backup da manha
scheduler.add_job(func=gerar_backup_automatico, trigger="cron", hour=9, minute=15)

# backup da tarde
scheduler.add_job(func=gerar_backup_automatico, trigger="cron", hour=17, minute=30)
scheduler.start()


#rota do registo
@app.route('/api/register', methods=['POST'])
def register():
    dados = request.get_json()
    username = dados.get('username')
    password = dados.get('password')

    if not username or not password:
        return jsonify({"error": "Preenche o username e a password"}), 400

    #verifica se o user ja existe
    utilizador_existente = User.query.filter_by(username=username).first()
    if utilizador_existente:
        utilizador_existente = User.query.filter_by(username=username). first()
        return jsonify({"error": "Esse username já existe!"}), 400

    #encripta a password antes de guardar
    password_criptografada = generate_password_hash(password)

    novo_utilizador = User(username=username, password=password_criptografada)

    db.session.add(novo_utilizador)
    db.session.commit()

    return jsonify({"message": "Utilizador registado com sucesso!"}), 201
     

#rota login
@app.route('/api/login', methods=['POST'])
def login():
    dados = request.get_json()
    username = dados.get('username')
    password = dados.get('password')

    if not username or not password:
        return jsonify({"error": "Preenche o username e a password!"}), 400

    #procurar o user na bd
    utilizador = User.query.filter_by(username=username).first()

    #verificar se o user existe e se a password esta certa
    if not utilizador or not check_password_hash(utilizador.password, password):
        return jsonify({"error": "Credênciais inválidas!"}), 401

    #se estives tudo certo, cria JWT token associado ao user ou ID
    access_token = create_access_token(identity=str(utilizador.id))

    return jsonify({
        "message": "login efetuado com sucesso!",
        "access_token": access_token
    }), 200


@app.route('/api/protegida', methods=['GET'])
@jwt_required()
def rota_protegida():
    # Descobre qual é o ID do utilizador que está a usar o token
    utilizador_id = get_jwt_identity()
    return jsonify({
        "message": "Acesso autorizado com sucesso!",
        "utilizador_id": utilizador_id
    }), 200


#ligar 
if __name__ == '__main__':
    app.run(debug=True)

 