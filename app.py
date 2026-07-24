import os
from flask import Flask , jsonify, request
from flask_sqlalchemy import SQLAlchemy

#criar API
app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:root@localhost/teste_monitor'

#desligar avisos flask
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

#users
class Utilizador(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)


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
            'nome': self.nome
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
            'data_hora': self.data_hora,
            'caminho_id': self.caminho_id
        }

#construir
with app.app_context():
    db.create_all()


#1 rota
@app.route('/')
def pagina_principal():
    return 'funcional'

#rota para adicionar user teste
@app.route('/adicionar_teste')
def adicionar_teste():
   # user = Utilizador(nome='João', email='joao@example.com')

    #db.session.add(user)

    #db.session.commit()

    return 'User adicionado com sucesso!'

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

#cria o proj na memoria
    novo_projeto = Projeto(
        nome=dados['nome'],
    )


#rota para listar os projs
@app.route('/projetos', methods=['GET'])
def listar_projetos():
    todos_projetos = Projeto.query.all()
    resultado = [projeto.to_dict() for projeto in todos_projetos]

    return jsonify(resultado), 200


#grava na bd
    db.session.add(novo_projeto)
    db.session.commit()

    return jsonify(novo_projeto.to_dict()), 201

#rota para ver todos os projetos
@app.route('/projetos', methods=['GET'])
def lver_projetos():
    projetos = Projeto.query.all()


    return jsonify([projeto.to_dict() for projeto in projetos]), 200


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

#ligar 
if __name__ == '__main__':
    app.run(debug=True)

 