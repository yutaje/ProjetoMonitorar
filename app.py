from fileinput import filename
import os
from flask import Flask , jsonify, request, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime
import json
from apscheduler.schedulers.background import BackgroundScheduler
from flask_jwt_extended import JWTManager, create_access_token
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt, verify_jwt_in_request
from functools import wraps
from dotenv import load_dotenv
import psutil
import shutil
import subprocess
import string




PASTA_BACKUPS = 'backups_diarios'
os.makedirs(PASTA_BACKUPS, exist_ok=True)


#criar API
app = Flask(__name__)
CORS(app)


load_dotenv()


app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY")


jwt = JWTManager(app)


#verifica se tem token e se é admin
def admin_required(fn):
    @wraps(fn)
    def decorator(*args, **kwargs):
        #obriga a ter token valido
        verify_jwt_in_request()

        #le o que esta dentro do token
        claims = get_jwt()

        #verifica se a role guardada no token é admin
        if claims.get("role") == "admin":
            return fn(*args, **kwargs)
        else:
            return jsonify({"error": "Acesso negado! Esta área é exclusiva para Administradores."}), 403
    return decorator


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


class ComputadorRede(db.Model):
    __tablename__ = 'computador_rede'

    id = db.Column(db.Integer, primary_key=True)
    nome_pc = db.Column(db.String(150), nullable=False)
    ip = db.Column(db.String(50), nullable=False)
    utilizador_rede = db.Column(db.String(100), nullable=True)
    password_rede = db.Column(db.String(200), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'nome_pc': self.nome_pc,
            'ip': self.ip,
            'utilizador_rede': self.utilizador_rede,
            # Por segurança, podemos omitir a password no dicionário geral se não for estritamente necessário expô-la
        }    


class Caminho(db.Model):
    __tablename__ = 'caminho'

    id = db.Column(db.Integer, primary_key=True)

    localizacao = db.Column(db.String(500),nullable=False)

    projeto_id = db.Column(db.Integer, db.ForeignKey('projeto.id'), nullable=False)

    data_ultima_atividade = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'localizacao': self.localizacao,
            'projeto_id': self.projeto_id,
            'data_ultima_atividade': str(self.data_ultima_atividade) if self.data_ultima_atividade else None
        }


class Historico(db.Model):
    __tablename__ = 'historico'

    id = db.Column(db.Integer, primary_key=True)

    caminho_id = db.Column(db.Integer, db.ForeignKey('caminho.id'), nullable=False)

    data_verificacao = db.Column(db.DateTime, default=db.func.now(), nullable=False)

    estado = db.Column(db.String(50), nullable=False)

    total_ficheiros = db.Column(db.Integer, default=0, nullable=False)

    extensoes_detalhe = db.Column(db.Text, nullable=True)

    detalhes = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'data_verificacao': str(self.data_verificacao),
            'caminho_id': self.caminho_id,
            'estado': self.estado,
            'total_ficheiros': self.total_ficheiros,
            'extensoes_detalhe': json.loads(self.extensoes_detalhe) if  self.extensoes_detalhe else {},
            'detalhes': self.detalhes
        }


class LogAtividade(db.Model):
    __tablename__ = 'log_atividade'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    acao = db.Column(db.String(255), nullable=False)
    detalhes = db.Column(db.Text, nullable=True)
    data_hora = db.Column(db.DateTime, default=db.func.now(), nullable=False)

    def to_dict(self):
        # Podes fazer join com o User para devolver logo o username no JSON
        user = User.query.get(self.user_id)
        return {
            "id": self.id,
            "username": user.username if user else "Desconhecido",
            "acao": self.acao,
            "detalhes": self.detalhes,
            "data_hora": str(self.data_hora)
        }


def registar_log(user_id, acao, detalhes=None):
    novo_log = LogAtividade(user_id=user_id, acao=acao, detalhes=detalhes)
    db.session.add(novo_log)
    db.session.commit()


class Alerta(db.Model):
    __tablename__ = 'alerta'

    id = db.Column(db.Integer, primary_key=True)
    projeto_id = db.Column(db.Integer, db.ForeignKey('projeto.id'), nullable=False)
    caminho_id = db.Column(db.Integer, db.ForeignKey('caminho.id'), nullable=False)
    data_hora = db.Column(db.DateTime, default=db.func.now(), nullable=False)
    tipo_erro = db.Column(db.String(200), nullable=False) 
    estado_alerta = db.Column(db.String(50), default='Por resolver', nullable=False)

    def to_dict(self):
        # Ir buscar o nome do projeto e o caminho à base de dados usando os IDs
        projeto = Projeto.query.get(self.projeto_id)
        caminho = Caminho.query.get(self.caminho_id)
        
        return {
            'id': self.id,
            'projeto_id': self.projeto_id,
            'nome_projeto': projeto.nome if projeto else "Projeto Desconhecido",
            'caminho_id': self.caminho_id,
            'localizacao': caminho.localizacao if caminho else "Caminho apagado",
            'data_hora': str(self.data_hora),
            'tipo_erro': self.tipo_erro,
            'estado_alerta': self.estado_alerta
        }


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    #guardar a passe encriptada
    password = db.Column(db.String(200), nullable=False)

    role = db.Column(db.String(20), default='user', nullable=False)

    def to_dict(self):
        return{
            "id": self.id,
            "username": self.username,
            "role": self.role
        }


#tabela para guardar as configurações do sistema na bd
class ConfigSistema(db.Model):
    __tablename__ = 'config_sistema'

    id = db.Column(db.Integer, primary_key=True)
    chave = db.Column(db.String(100), unique=True, nullable=False)
    valor = db.Column(db.String(255), nullable=False)

    def to_dict(self):
        return {
            "chave": self.chave,
            "valor": self.valor
        }


def construir_arvore_pasta(caminho_dir):
    nome = os.path.basename(caminho_dir) or caminho_dir
    total_ficheiros = 0
    extensoes_dict = {}
    subpastas = []
    data_mais_recente = None
    
    is_rede = caminho_dir.startswith('\\\\')
    
    try:
        # Para pastas de rede, evitamos o os.path.exists estrito para prevenir bloqueios por timeout/latência
        if not is_rede and not os.path.exists(caminho_dir):
            raise FileNotFoundError("A pasta não foi encontrada.")
            
        itens = os.listdir(caminho_dir)
    except PermissionError:
        return {
            "nome": nome,
            "caminho": caminho_dir,
            "erro": "Permissão negada",
            "total_ficheiros": 0,
            "extensoes": {},
            "subpastas": [],
            "data_mais_recente": None
        }
    except Exception as e:
        return {
            "nome": nome,
            "caminho": caminho_dir,
            "erro": str(e),
            "total_ficheiros": 0,
            "extensoes": {},
            "subpastas": [],
            "data_mais_recente": None
        }

    for item in itens:
        if item.startswith('.'):
            continue

        item_path = os.path.join(caminho_dir, item)
        try:
            if os.path.isdir(item_path):
                sub_arvore = construir_arvore_pasta(item_path)
                total_ficheiros += sub_arvore["total_ficheiros"]
                for ext, count in sub_arvore["extensoes"].items():
                    extensoes_dict[ext] = extensoes_dict.get(ext, 0) + count
                subpastas.append(sub_arvore)
            elif os.path.isfile(item_path):
                total_ficheiros += 1
                _, ext = os.path.splitext(item)
                ext = ext.lower()
                if ext:
                    extensoes_dict[ext] = extensoes_dict.get(ext, 0) + 1
        except Exception:
            continue

    return {
        "nome": nome,
        "caminho": caminho_dir,
        "total_ficheiros": total_ficheiros,
        "extensoes": extensoes_dict,
        "subpastas": subpastas,
        "data_mais_recente": data_mais_recente
    }


def executar_scan_caminho(caminho_obj):
    localizacao = caminho_obj.localizacao
    projeto_id = caminho_obj.projeto_id
    
    estado_atual = "OK"
    detalhes_msg = "A pasta existe e está acessível."
    tipo_erro_alerta = None
    total_ficheiros = 0
    arvore_completa = {}
    data_recente_encontrada = None # <--- NOVIDADE

    is_rede = localizacao.startswith('\\\\')

    try:
        if not is_rede and not os.path.exists(localizacao):
            raise FileNotFoundError("A pasta não foi encontrada ou o caminho é inválido.")
        
        arvore_completa = construir_arvore_pasta(localizacao)
        
        if is_rede and arvore_completa.get("erro"):
            raise OSError(arvore_completa["erro"])

        total_ficheiros = arvore_completa["total_ficheiros"]
        data_recente_encontrada = arvore_completa.get("data_mais_recente") # <--- APANHA A DATA DA ÁRVORE

    except PermissionError:
        estado_atual = "ERRO"
        detalhes_msg = "Permissão negada para aceder a este diretório."
        tipo_erro_alerta = "Permissão negada"
    except FileNotFoundError:
        estado_atual = "ERRO"
        detalhes_msg = "Caminho não encontrado ou diretório inexistente."
        tipo_erro_alerta = "Caminho não encontrado"
    except OSError as e:
        if is_rede:
            estado_atual = "AVISO"
            detalhes_msg = f"Partilha de rede temporariamente inacessível ou lenta: {str(e)}"
            tipo_erro_alerta = None 
        else:
            estado_atual = "ERRO"
            detalhes_msg = f"Erro de sistema de ficheiros: {str(e)}"
            tipo_erro_alerta = "Rede inacessível / Erro de I/O"
    except Exception as e:
        estado_atual = "ERRO"
        detalhes_msg = f"Erro desconhecido: {str(e)}"
        tipo_erro_alerta = "Erro desconhecido"

    # <--- INÍCIO DA ATUALIZAÇÃO DA BASE DE DADOS (NOVO) --->
    if data_recente_encontrada:
        # Só atualizamos se tivermos encontrado uma data mais recente do que a que já lá estava
        if caminho_obj.data_ultima_atividade is None or data_recente_encontrada > caminho_obj.data_ultima_atividade:
            caminho_obj.data_ultima_atividade = data_recente_encontrada
    # <--- FIM DA ATUALIZAÇÃO DA BASE DE DADOS --->

    # Guarda o histórico na base de dados
    novo_historico = Historico(
        caminho_id=caminho_obj.id,
        estado=estado_atual,
        total_ficheiros=total_ficheiros,
        extensoes_detalhe=json.dumps(arvore_completa, ensure_ascii=False),
        detalhes=detalhes_msg
    )
    db.session.add(novo_historico)

    if estado_atual == "ERRO":
        alerta_existente = Alerta.query.filter_by(caminho_id=caminho_obj.id, estado_alerta='Por resolver').first()
        if not alerta_existente:
            novo_alerta = Alerta(
                projeto_id=projeto_id,
                caminho_id=caminho_obj.id,
                tipo_erro=tipo_erro_alerta,
                estado_alerta="Por resolver"
            )
            db.session.add(novo_alerta)

    db.session.commit()
    return estado_atual, total_ficheiros


def obter_letra_livre():
    # Percorre o alfabeto de trás para a frente (Z até E)
    for letra in reversed(string.ascii_uppercase):
        if letra not in ['A', 'B', 'C', 'D']: # Evita as drives normais do sistema
            letra_caminho = f"{letra}:\\"
            # Se a letra não existir no PC no momento, devolve essa!
            if not os.path.exists(letra_caminho):
                return f"{letra}:"
    return None


def cacar_partilha_remota(ip, utilizador, password):
    """
    Entra no IPC$, faz o net view, e procura uma pasta partilhada válida,
    ignorando pastas restritas de projetos (como CMPORTO).
    """
    # 1. Autenticar no IPC$
    comando_ipc = ["net", "use", f"\\\\{ip}\\IPC$", f"/user:{utilizador}", password]
    subprocess.run(comando_ipc, capture_output=True, text=True, shell=False)

    # 2. Perguntar ao PC as partilhas dele
    comando_view = ["net", "view", f"\\\\{ip}"]
    resultado_view = subprocess.run(comando_view, capture_output=True, text=True, shell=False)

    partilhas_candidatas = []
    linhas = resultado_view.stdout.splitlines()
    ler_dados = False

    # Lista Negra: Pastas que sabemos que dão Erro 5 ou são de projeto
    blacklist = ["cmporto", "admin", "backup", "prints", "fax"]

    # 3. Ler o output e recolher as pastas válidas
    for linha in linhas:
        if linha.startswith("----"):
            ler_dados = True
            continue
            
        if ler_dados and linha.strip():
            if "concluído" in linha.lower() or "completed" in linha.lower():
                continue
                
            partes = linha.split()
            nome_partilha = partes[0]
            
            # Ignora se estiver na blacklist
            if nome_partilha.lower() in blacklist:
                continue

            tipo_partilha = partes[1].lower() if len(partes) > 1 else ""
            
            # Se for explicitamente do tipo disco, pomos logo no topo da lista
            if "disco" in tipo_partilha or "disk" in tipo_partilha:
                partilhas_candidatas.insert(0, nome_partilha)
            else:
                partilhas_candidatas.append(nome_partilha)

    # 4. Fechar a ligação da receção
    subprocess.run(["net", "use", f"\\\\{ip}\\IPC$", "/delete", "/y"], capture_output=True, shell=False)

    # Devolve a primeira candidata válida que não seja restrita (ou None se não houver nenhuma)
    return partilhas_candidatas[0] if partilhas_candidatas else None


# Rota para descarregar o ficheiro .reg diretamente da raiz do projeto
@app.route('/api/download/reg', methods=['GET'])
def download_reg_file():
    # app.root_path é a diretoria principal do teu projeto (PROJETOMONITORAR)
    return send_from_directory(
        directory=app.root_path, 
        path='monitorapp.reg', 
        as_attachment=True
    )


@app.route('/api/backups/download/<filename>', methods=['GET'])
@jwt_required()
def download_backup(filename):
    
    pasta_backups = 'backups_diarios' 
    
    try:
        # as_attachment=True força o browser a fazer o download em vez de tentar abrir o JSON no ecrã
        return send_from_directory(pasta_backups, filename, as_attachment=True)
    except FileNotFoundError:
        return {"sucesso": False, "erro": "Ficheiro não encontrado no servidor."}, 404


@app.route('/api/admin/logs', methods=['GET'])
@admin_required
def listar_logs():
    logs = LogAtividade.query.order_by(LogAtividade.data_hora.desc()).all()
    return jsonify([log.to_dict() for log in logs]), 200


@app.route('/api/computadores/<int:pc_id>/espaco', methods=['GET'])
@jwt_required()
def verificar_espaco_pc(pc_id):
    pc = ComputadorRede.query.get_or_404(pc_id)
    
    if not pc.ip:
        return jsonify({"sucesso": False, "erro": "O IP do computador não está definido."}), 400
        
    # --- CENÁRIO 1: É o PC Local ---
    if pc.ip == "127.0.0.1" or pc.ip.lower() == "localhost":
        try:
            uso = shutil.disk_usage("C:\\")
            total_gb = round(uso.total / (2**30), 2)
            livre_gb = round(uso.free / (2**30), 2)
            usado_gb = round(uso.used / (2**30), 2)
            percentagem = round((uso.used / uso.total) * 100, 1)
            
            return jsonify({
                "sucesso": True,
                "discos": [{
                    "letra": "C", "total_gb": total_gb, "livre_gb": livre_gb,
                    "usado_gb": usado_gb, "percentagem": percentagem
                }]
            }), 200
        except Exception as e:
            return jsonify({"sucesso": False, "erro": str(e)}), 500

    # --- CENÁRIO 2: É um PC Remoto na Rede ---
    if not pc.utilizador_rede or not pc.password_rede:
        return jsonify({"sucesso": False, "erro": "Faltam credenciais de rede para este PC."}), 400

    # Pede ao sistema uma letra que não esteja a ser usada
    letra_drive = obter_letra_livre()
    if not letra_drive:
         return jsonify({"sucesso": False, "erro": "O servidor ficou sem letras de unidade disponíveis."}), 500
    
    try:
        nome_partilha = cacar_partilha_remota(pc.ip, pc.utilizador_rede, pc.password_rede)

        
        if not nome_partilha:
            return jsonify({"sucesso": False, "erro": f"Nenhuma pasta partilhada encontrada no IP {pc.ip}."}), 404
            
        caminho_rede = f"\\\\{pc.ip}\\{nome_partilha}"
        
        # Mapeia a unidade dinâmica para a partilha encontrada
        comando_map = ["net", "use", letra_drive, caminho_rede, f"/user:{pc.utilizador_rede}", pc.password_rede]
        resultado_map = subprocess.run(comando_map, capture_output=True, text=True, shell=False)
        
        if resultado_map.returncode != 0:
            return jsonify({"sucesso": False, "erro": f"Erro a mapear partilha: {resultado_map.stderr}"}), 500
            
        # Extrai os dados do disco com base na letra dinâmica que calhou
        uso = shutil.disk_usage(f"{letra_drive}\\")
        total_gb = round(uso.total / (2**30), 2)
        livre_gb = round(uso.free / (2**30), 2)
        usado_gb = round(uso.used / (2**30), 2)
        percentagem = round((uso.used / uso.total) * 100, 1)
        
        # Limpa a ligação no fim
        subprocess.run(["net", "use", letra_drive, "/delete", "/y"], capture_output=True, shell=False)
        
        return jsonify({
            "sucesso": True,
            "discos": [{
                "letra": "C", 
                "total_gb": total_gb, 
                "livre_gb": livre_gb,
                "usado_gb": usado_gb, 
                "percentagem": percentagem,
                "nota_tecnica": f"Lido via pasta partilhada '{nome_partilha}' em {letra_drive}"
            }]
        }), 200
        
    except Exception as e:
        print(f"\n[ERRO FATAL] PC {pc.ip}: {str(e)}\n")
        subprocess.run(["net", "use", letra_drive, "/delete", "/y"], capture_output=True, shell=False)
        return jsonify({"sucesso": False, "erro": f"Erro de ligação: {str(e)}"}), 500


#motor de pesquisa
@app.route('/api/projetos/pesquisa', methods=['GET'])
@jwt_required()
def pesquisa_projetos():
    #parametros de pesquisa opcionais
    termo = request.args.get('termo', '').strip()
    modo = request.args.get('modo', 'historico').lower()

    #filtra os projs pelo nome se o termo for fornecido
    if termo:
        projetos = Projeto.query.filter(Projeto.nome.ilike(f"%{termo}%")).all()
    else:
        projetos = Projeto.query.all()

    resultado_final = []

    for projeto in projetos:
        caminhos = Caminho.query.filter_by(projeto_id=projeto.id).all()
        caminhos_info = []
        total_ficheiros_projeto = 0

        for caminho in caminhos:
            # vai buscar o ultimo historico na bd para este caminho
            ultimo_hist = Historico.query.filter_by(caminho_id=caminho.id).order_by(Historico.data_verificacao.desc()).first()

            if modo == 'temporeal':
                # modo irt executa o scan na hora
                estado, total = executar_scan_caminho(caminho)
                
               
                if estado not in ["OK", "Acessível", "Ativo"]: 
                    
                    # procura pelos alertas com estado 'por resolver'
                    alerta_existente = Alerta.query.filter_by(caminho_id=caminho.id, estado_alerta='Por resolver').first()
                    
                    if not alerta_existente:
                        novo_alerta = Alerta(
                            projeto_id=projeto.id,
                            caminho_id=caminho.id,
                            tipo_erro=f"Erro de acesso: {estado}",
                            estado_alerta='Por resolver' # <-- ESTAVA AQUI O ERRO!
                        )
                        db.session.add(novo_alerta)
                        db.session.commit()
                

                # atualiza a ref do ultimo historico depois do scan
                ultimo_hist = Historico.query.filter_by(caminho_id=caminho.id).order_by(Historico.data_verificacao.desc()).first()
            else:
                # modo historico, usa o que ja estava na bd
                estado = ultimo_hist.estado if ultimo_hist else "Sem registo"
                total = ultimo_hist.total_ficheiros if ultimo_hist else 0

            total_ficheiros_projeto += total
            
            #tratamento seguro das extensões JSON
            extensoes_dict = {}
            if ultimo_hist and ultimo_hist.extensoes_detalhe:
                try:
                    extensoes_dict = json.loads(ultimo_hist.extensoes_detalhe)
                except:
                    extensoes_dict = {}

            caminhos_info.append({
                "caminho_id": caminho.id,
                "localizacao": caminho.localizacao,
                "estado": estado,
                "total_ficheiros": total,
                "extensoes": extensoes_dict,
                "data_ultima_verificacao": str(ultimo_hist.data_verificacao) if ultimo_hist else None
            })
            
        #agrupa os caminhos ao projeto
        resultado_final.append({
            "projeto_id": projeto.id,
            "nome_projeto": projeto.nome,
            "caminhos": caminhos_info,
            "contagem_total_projeto": total_ficheiros_projeto
        })

    
    return jsonify({
        "modo_utilizado": modo,
        "resultados": resultado_final
    }), 200


# Rota para listar todos os PCs registados na rede
@app.route('/api/computadores', methods=['GET'])
@jwt_required()
def listar_computadores_rede():
    computadores = ComputadorRede.query.all()
    return jsonify([pc.to_dict() for pc in computadores]), 200


# Rota para registar um novo PC na rede
@app.route('/api/computadores', methods=['POST'])
@admin_required
def criar_computador_rede():
    dados = request.get_json()
    nome_pc = dados.get('nome_pc', '').strip()
    ip = dados.get('ip', '').strip()
    utilizador_rede = dados.get('utilizador_rede', '').strip()
    password_rede = dados.get('password_rede', '').strip()

    if not nome_pc or not ip:
        return jsonify({"erro": "O nome do PC e o endereço IP são obrigatórios!"}), 400

    novo_pc = ComputadorRede(
        nome_pc=nome_pc,
        ip=ip,
        utilizador_rede=utilizador_rede,
        password_rede=password_rede
    )

    db.session.add(novo_pc)
    db.session.commit()

    # Registar log da ação
    user_id = int(get_jwt_identity())
    registar_log(
        user_id=user_id,
        acao="CRIAR_COMPUTADOR_REDE",
        detalhes=f" Registou o PC '{nome_pc}' (IP: {ip}) no inventário de rede."
    )

    return jsonify({
        "mensagem": "Computador registado com sucesso!",
        "computador": novo_pc.to_dict()
    }), 201


@app.route('/api/computadores/<int:pc_id>', methods=['PUT'])
def editar_computador(pc_id):
    pc = ComputadorRede.query.get_or_404(pc_id) # Corrigido para ComputadorRede
    dados = request.get_json()
    
    pc.nome_pc = dados.get('nome_pc', pc.nome_pc)
    pc.ip = dados.get('ip', pc.ip)
    pc.utilizador_rede = dados.get('utilizador_rede', pc.utilizador_rede)
    
    password = dados.get('password_rede')
    if password:
        pc.password_rede = password
        
    db.session.commit()
    return jsonify({"sucesso": True, "mensagem": "Computador atualizado com sucesso!"}), 200


# Rota para apagar um PC do inventário
@app.route('/api/computadores/<int:id_pc>', methods=['DELETE'])
@admin_required
def apagar_computador_rede(id_pc):
    pc = ComputadorRede.query.get_or_404(id_pc)
    nome_pc = pc.nome_pc

    db.session.delete(pc)
    db.session.commit()

    user_id = int(get_jwt_identity())
    registar_log(
        user_id=user_id,
        acao="APAGAR_COMPUTADOR_REDE",
        detalhes=f"Removeu o PC '{nome_pc}' do inventário de rede."
    )

    return jsonify({"mensagem": f"Computador '{nome_pc}' removido com sucesso!"}), 200


def procurar_em_subpastas(no_subpasta, termo_lower, projeto_info, resultados_lista):
    if not no_subpasta or not isinstance(no_subpasta, dict):
        return

    nome_atual = no_subpasta.get("nome", "").lower()
    caminho_atual = no_subpasta.get("caminho", "")

    if termo_lower in nome_atual:
        if not any(r['caminho'] == caminho_atual for r in resultados_lista):
            resultados_lista.append({
                "id_projeto": projeto_info.id,
                "nome": f"{projeto_info.nome} > {no_subpasta.get('nome')}",
                "id_caminho": None,
                "caminho": caminho_atual
            })

    for sub in no_subpasta.get("subpastas", []):
        procurar_em_subpastas(sub, termo_lower, projeto_info, resultados_lista)

@app.route('/api/pesquisa-global', methods=['GET'])
@jwt_required()
def pesquisa_global_rapida():
    termo = request.args.get('q', '').strip()
    
    if not termo:
        return jsonify({"erro": "Termo de pesquisa vazio"}), 400

    termo_escapado = termo.replace('\\', '\\\\')
    termo_lower = termo.lower()

    resultados = []
    
    resultados_query = db.session.query(Projeto, Caminho)\
        .join(Caminho, Caminho.projeto_id == Projeto.id)\
        .filter(
            (Projeto.nome.ilike(f"%{termo_escapado}%")) | 
            (Caminho.localizacao.ilike(f"%{termo_escapado}%"))
        ).all()

    for projeto, caminho in resultados_query:
        resultados.append({
            "id_projeto": projeto.id,
            "nome": projeto.nome,
            "id_caminho": caminho.id,
            "caminho": caminho.localizacao
        })

    todos_caminhos = Caminho.query.all()
    for caminho in todos_caminhos:
        ultimo_hist = Historico.query.filter_by(caminho_id=caminho.id).order_by(Historico.data_verificacao.desc()).first()
        if ultimo_hist and ultimo_hist.extensoes_detalhe:
            try:
                arvore_json = json.loads(ultimo_hist.extensoes_detalhe)
                projeto_obj = Projeto.query.get(caminho.projeto_id)
                if projeto_obj:
                    procurar_em_subpastas(arvore_json, termo_lower, projeto_obj, resultados)
            except Exception:
                continue
    
    return jsonify({
        "termo": termo,
        "total": len(resultados),
        "resultados": resultados
    }), 200


@app.route('/api/pesquisa-lote', methods=['POST'])
@jwt_required()
def pesquisa_lote():
    dados = request.get_json()
    linhas = dados.get('linhas', [])
    modo = dados.get('modo', 'contem')
    fonte = dados.get('fonte', 'bd')
    projetos_ids = dados.get('projetos_ids', []) # <--- NOVO: Lista de IDs selecionados (ex: [1, 3])

    if not linhas:
        return jsonify({"erro": "Nenhum termo fornecido para pesquisa."}), 400

    encontrados = []
    nao_encontrados = []

    # (Carregamento de backups mantêm-se igual...)
    todos_os_backups = []
    try:
        if os.path.exists(PASTA_BACKUPS):
            for f_name in os.listdir(PASTA_BACKUPS):
                if f_name.endswith('.json'):
                    caminho_f = os.path.join(PASTA_BACKUPS, f_name)
                    with open(caminho_f, 'r', encoding='utf-8') as f_bk:
                        dados_bk = json.load(f_bk)
                        todos_os_backups.append((f_name, dados_bk))
    except Exception:
        pass

    if fonte == 'backups':
        for linha in linhas:
            termo = linha.strip()
            if not termo:
                continue

            matches_por_termo = []
            for f_name, dados_bk in todos_os_backups:
                projetos_bk = {p['id']: p['nome'] for p in dados_bk.get('projetos', [])}
                for c in dados_bk.get('caminhos', []):
                    localizacao = c.get('localizacao', '')
                    proj_id = c.get('projeto_id')
                    proj_nome = projetos_bk.get(proj_id, 'Desconhecido')

                    # Filtro opcional por projetos_ids vindos do frontend
                    if projetos_ids and proj_id not in projetos_ids:
                        continue

                    match = False
                    if modo == 'exato':
                        if termo.lower() == proj_nome.lower() or termo.lower() == localizacao.lower():
                            match = True
                    else:
                        if termo.lower() in proj_nome.lower() or termo.lower() in localizacao.lower():
                            match = True

                    if match:
                        encontrado_idx = next((i for i, m in enumerate(matches_por_termo) if m['caminho'].lower() == localizacao.lower()), None)
                        if encontrado_idx is not None:
                            if f_name not in matches_por_termo[encontrado_idx]['backups']:
                                matches_por_termo[encontrado_idx]['backups'].append(f_name)
                        else:
                            matches_por_termo.append({
                                "id_projeto": proj_id,
                                "nome": proj_nome,
                                "caminho": localizacao,
                                "backups": [f_name]
                            })

            if matches_por_termo:
                encontrados.append({"termo_pesquisado": termo, "resultados": matches_por_termo})
            else:
                nao_encontrados.append(termo)
    else:
        # Pesquisa na Base de Dados com filtro opcional de projetos
        for linha in linhas:
            termo = linha.strip()
            if not termo:
                continue

            termo_escapado = termo.replace('\\', '\\\\')
            
            query = db.session.query(Projeto, Caminho).join(Caminho, Caminho.projeto_id == Projeto.id)
            
            # Se o utilizador selecionou projetos específicos, aplicamos o filtro .in_()
            if projetos_ids:
                query = query.filter(Caminho.projeto_id.in_(projetos_ids))

            if modo == 'exato':
                resultados_query = query.filter((Projeto.nome == termo) | (Caminho.localizacao == termo)).all()
            else:
                resultados_query = query.filter((Projeto.nome.ilike(f"%{termo_escapado}%")) | (Caminho.localizacao.ilike(f"%{termo_escapado}%"))).all()

            if resultados_query:
                matches = []
                for projeto, caminho in resultados_query:
                    backups_do_projeto = []
                    for f_name, dados_bk in todos_os_backups:
                        proj_bk_ids = {p['id']: p['nome'] for p in dados_bk.get('projetos', [])}
                        encontrou_neste = False
                        for c_bk in dados_bk.get('caminhos', []):
                            loc_bk = c_bk.get('localizacao', '')
                            p_id = c_bk.get('projeto_id')
                            p_nome = proj_bk_ids.get(p_id, '')
                            if (str(p_id) == str(projeto.id) or projeto.nome.lower() in p_nome.lower()) and (caminho.localizacao.lower() in loc_bk.lower()):
                                encontrou_neste = True
                                break
                        if encontrou_neste:
                            backups_do_projeto.append(f_name)

                    matches.append({
                        "id_projeto": projeto.id,
                        "nome": projeto.nome,
                        "caminho": caminho.localizacao,
                        "backups": backups_do_projeto
                    })
                encontrados.append({"termo_pesquisado": termo, "resultados": matches})
            else:
                nao_encontrados.append(termo)

    return jsonify({
        "encontrados": encontrados,
        "nao_encontrados": nao_encontrados
    }), 200


#construir
with app.app_context():
    db.create_all()


@app.route('/')
def pagina_principal():
    return 'funcional'


#rota para o admin ver as configs atuais
@app.route('/api/admin/config', methods=['GET'])
@admin_required
def obter_configuracoes():
    configs = ConfigSistema.query.all()
    
    resultado = {c.chave: c.valor for c in configs}
    
    
    defaults = {
        "intervalo_scan_horas": resultado.get("intervalo_scan_horas", "2"),
        "hora_backup_manha": resultado.get("hora_backup_manha", "09:15"),
        "hora_backup_tarde": resultado.get("hora_backup_tarde", "17:30")
    }
    
    return jsonify(defaults), 200


#rota para atualizar as configs
@app.route('/api/admin/config', methods=['PUT'])
@admin_required
def atualizar_configuracoes():
    dados = request.get_json()
    
    if not dados:
        return jsonify({"error": "Dados inválidos."}), 400

    for chave, valor in dados.items():
        config = ConfigSistema.query.filter_by(chave=chave).first()
        if config:
            config.valor = str(valor)
        else:
            nova_config = ConfigSistema(chave=chave, valor=str(valor))
            db.session.add(nova_config)
            
    db.session.commit()

    #registar log da alteração
    user_id = int(get_jwt_identity())
    registar_log(
        user_id=user_id,
        acao="ATUALIZAR_CONFIG",
        detalhes="Alterou os parâmetros de agendamento (Scheduler) do sistema."
    )

    return jsonify({"message": "Configurações atualizadas com sucesso! Reinicie o agendamento se necessário."}), 200


#rota para listar todos os users
@app.route('/users')
@admin_required
def listar_users():
    todos_users = User.query.all()
    lista = []

    #percorrer users que vieram da bd
    for user in todos_users:
        lista.append({
            'id': user.id,
            'username': user.username,
            'role': user.role 
        })

    return jsonify(lista), 200


# Rota para criar um novo utilizador diretamente pelo painel de admin
@app.route('/api/users', methods=['POST'])
@admin_required
def criar_utilizador_admin():
    dados = request.get_json()
    username = dados.get('username')
    password = dados.get('password')
    role = dados.get('role', 'user')

    if not username or not password:
        return jsonify({"error": "O username e a password são obrigatórios!"}), 400

    # Verifica se o utilizador já existe
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Esse username já existe!"}), 400

    # Encripta a password
    password_criptografada = generate_password_hash(password)

    novo_utilizador = User(
        username=username.strip(),
        password=password_criptografada,
        role=role
    )

    db.session.add(novo_utilizador)
    db.session.commit()

    # Registar log da ação
    admin_id = get_jwt_identity()
    registar_log(
        user_id=admin_id,
        acao="CRIAR_UTILIZADOR",
        detalhes=f"Criou o utilizador '{novo_utilizador.username}' com o cargo '{role}'."
    )

    return jsonify({
        "message": "Utilizador criado com sucesso!",
        "user": novo_utilizador.to_dict()
    }), 201


# Rota para apagar um utilizador pelo ID
@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@admin_required
def apagar_utilizador_admin(user_id):
    admin_id_atual = int(get_jwt_identity())

    # Evitar que o admin apague a sua própria conta por engano
    if user_id == admin_id_atual:
        return jsonify({"error": "Não podes apagar a tua própria conta de administrador!"}), 400

    user = User.query.get_or_404(user_id)
    username_removido = user.username

    db.session.delete(user)
    db.session.commit()

    # Registar log da ação
    registar_log(
        user_id=admin_id_atual,
        acao="APAGAR_UTILIZADOR",
        detalhes=f"Apagou o utilizador '{username_removido}' (ID: {user_id})."
    )

    return jsonify({
        "message": f"Utilizador '{username_removido}' apagado com sucesso!"
    }), 200


#rota para alterar a role de um user
@app.route('/api/users/<int:user_id>/role', methods=['PUT'])
@admin_required
def alterar_cargo_utilizador(user_id):
    user = User.query.get_or_404(user_id)
    dados = request.get_json()
    
    nova_role = dados.get('role')
    
    if nova_role not in ['admin', 'user']:
        return jsonify({"error": "Cargo inválido! Escolha 'admin' ou 'user'."}), 400
        
    cargo_antigo = user.role
    user.role = nova_role
    db.session.commit()
    
    # Registar a ação nos logs do sistema
    admin_id = get_jwt_identity()
    registar_log(
        user_id=admin_id,
        acao="ALTERAR_CARGO",
        detalhes=f"Alterou o cargo do utilizador '{user.username}' de '{cargo_antigo}' para '{nova_role}'."
    )
    
    return jsonify({
        "message": f"Cargo do utilizador '{user.username}' atualizado para '{nova_role}' com sucesso!",
        "user": user.to_dict()
    }), 200


#rota para criar novo proj
@app.route('/projetos', methods=['POST'])
@jwt_required()
def criar_projeto():
    dados = request.get_json()

    if not dados or 'nome' not in dados:
        return jsonify({"erro": "Falta o campo 'nome' no pedido JSON."}), 400

    nome_limpo = dados['nome'].strip()
    if not nome_limpo:
        return jsonify({"erro": "O nome do projeto não pode estar vazio."}), 400

    novo_projeto = Projeto(nome=nome_limpo)
    db.session.add(novo_projeto)
    db.session.commit()

    # Registar log da criação do projeto
    user_id = int(get_jwt_identity())
    registar_log(
        user_id=user_id,
        acao="CRIAR_PROJETO",
        detalhes=f"Criou o projeto '{novo_projeto.nome}' (ID: {novo_projeto.id})."
    )

    return jsonify(novo_projeto.to_dict()), 201


#rota para listar os projs
@app.route('/projetos', methods=['GET'])
@jwt_required()
def listar_projetos():
    todos_projetos = Projeto.query.all()
    resultado = [projeto.to_dict() for projeto in todos_projetos]

    return jsonify(resultado), 200


#rota para apagar um proj
@app.route('/projetos/<int:projeto_id>', methods=['DELETE'])
@admin_required
def apagar_projeto(projeto_id):
    projeto = Projeto.query.get_or_404(projeto_id)
    nome_projeto = projeto.nome

    # 1. APAGA TODOS OS ALERTAS DESTE PROJETO PRIMEIRO
    Alerta.query.filter_by(projeto_id=projeto.id).delete()

    # 2. Apaga históricos de todos os caminhos associados
    caminhos_associados = Caminho.query.filter_by(projeto_id=projeto.id).all()
    for caminho in caminhos_associados:
        Historico.query.filter_by(caminho_id=caminho.id).delete()

    # 3. Apaga os caminhos
    Caminho.query.filter_by(projeto_id=projeto.id).delete()
    
    # 4. Finalmente apaga o projeto
    db.session.delete(projeto)
    db.session.commit()

    # Registar log da eliminação
    user_id = int(get_jwt_identity())
    registar_log(
        user_id=user_id,
        acao="APAGAR_PROJETO",
        detalhes=f"Apagou o projeto '{nome_projeto}' e respetivos caminhos/alertas."
    )

    return jsonify({
        "mensagem": f"O projeto '{projeto.nome}' e todos os seus registos foram apagados com sucesso!"
    }), 200

#rota para editar um proj
@app.route('/projetos/<int:id>', methods=['PUT'])
@jwt_required()
def editar_projeto(id):
    projeto = Projeto.query.get(id)
    if not projeto:
        return jsonify({"erro": "Projeto não encontrado."}), 404

    dados = request.get_json()
    if not dados or 'nome' not in dados:
        return jsonify({"erro": "Falta o campo 'nome' no pedido JSON."}), 400

    nome_limpo = dados['nome'].strip()
    if not nome_limpo:
        return jsonify({"erro": "O nome do projeto não pode estar vazio."}), 400

    nome_antigo = projeto.nome
    projeto.nome = nome_limpo
    db.session.commit()

    # Registar log da alteração do projeto
    user_id = int(get_jwt_identity())
    registar_log(
        user_id=user_id,
        acao="EDITAR_PROJETO",
        detalhes=f"Alterou o nome do projeto de '{nome_antigo}' para '{nome_limpo}'."
    )

    return jsonify(projeto.to_dict()), 200


#rota para apagar um caminho individual
@app.route('/caminhos/<int:caminho_id>', methods=['DELETE'])
@admin_required
def apagar_caminho(caminho_id):
    #procura o caminho pelo ID
    caminho = Caminho.query.get_or_404(caminho_id)

    # 1. APAGA OS ALERTAS ASSOCIADOS A ESTE CAMINHO PRIMEIRO
    Alerta.query.filter_by(caminho_id=caminho.id).delete()

    # 2. apaga o historico associado a pasta
    Historico.query.filter_by(caminho_id=caminho.id).delete()

    # 3. apaga o caminho
    db.session.delete(caminho)

    #grava na bd
    db.session.commit()

    return jsonify({
        "mensagem": f"O caminho '{caminho.localizacao}', alertas e histórico foram apagados com sucesso!"
    }), 200


#rota para editar um caminho individual
@app.route('/caminhos/<int:id>', methods=['PUT'])
@jwt_required()
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
@jwt_required()
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
@jwt_required()
def verificar_caminho(caminho_id):
    #vai buscar o caminho a bd, se nao existir devolve 404
    caminho_obj = Caminho.query.get_or_404(caminho_id)
    
    
    estado, total = executar_scan_caminho(caminho_obj)

    # vai buscar o ultimo historico gravado para devolver os detalhes e extensoes
    ultimo_historico = Historico.query.filter_by(caminho_id=caminho_obj.id).order_by(Historico.data_verificacao.desc()).first()

    return jsonify({
        "mensagem": "Varredura física concluída com sucesso.",
        "caminho_id": caminho_obj.id,
        "localizacao": caminho_obj.localizacao,
        "estado": estado,
        "total_ficheiros": total,
        "extensoes": ultimo_historico.to_dict()["extensoes_detalhe"],
        "detalhes": ultimo_historico.detalhes,
        "data_verificacao": str(ultimo_historico.data_verificacao)
    }), 200


@app.route('/caminhos/<int:caminho_id>', methods=['PUT'])
@jwt_required()
def atualizar_caminho(caminho_id):
    # vai buscar o caminho a bd
    caminho_obj = Caminho.query.get_or_404(caminho_id)
    
    # le o JSON  
    dados = request.get_json()
    
    # atualiza a localização se ela vier no JSON
    if 'localizacao' in dados:
        caminho_obj.localizacao = dados['localizacao']
        db.session.commit()
        return jsonify({
            "mensagem": "Caminho atualizado com sucesso na Base de Dados!",
            "nova_localizacao": caminho_obj.localizacao
        }), 200
        
    return jsonify({"erro": "Nenhuma localização fornecida no JSON."}), 400


#rota para listar caminhos de um proj
@app.route('/projetos/<int:projeto_id>/caminhos', methods=['GET'])
@jwt_required()
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
@jwt_required()
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
@admin_required
def obter_estatisticas():
    #conta quantos registos existem em cada tabela
    total_projetos = Projeto.query.count()
    total_caminhos = Caminho.query.count()
    total_verificacoes = Historico.query.count()
    
    #contagem de alertas 
    alertas_pendentes = Alerta.query.filter_by(estado_alerta='Por resolver').count()
    alertas_resolvidos = Alerta.query.filter_by(estado_alerta='Resolvido').count()

    #prep do relatorio final em JSON
    relatorio = {
        "dashboard": {
            "projetos_ativos": total_projetos,
            "caminhos_monitorizados": total_caminhos,
            "verificacoes_realizadas": total_verificacoes,
            "saude_sistema": {
                "alertas_pendentes": alertas_pendentes,
                "alertas_resolvidos": alertas_resolvidos
            }
        }
    }

    return jsonify(relatorio), 200

#rota para o indice
@app.route('/api/backups', methods=['GET'])
@jwt_required()
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
@jwt_required()
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
@admin_required
def criar_backup_manual():
    try:
        caminhos = Caminho.query.all()
        projetos = Projeto.query.all()

        # Enriquecer os caminhos com o último histórico (incluindo a árvore hierárquica)
        caminhos_com_historico = []
        for c in caminhos:
            c_dict = c.to_dict()
            ultimo_hist = Historico.query.filter_by(caminho_id=c.id).order_by(Historico.data_verificacao.desc()).first()
            if ultimo_hist:
                c_dict['ultimo_historico'] = ultimo_hist.to_dict()
            else:
                c_dict['ultimo_historico'] = None
            caminhos_com_historico.append(c_dict)

        dados_para_guardar = {
            "data_backup": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "caminhos": caminhos_com_historico,
            "projetos": [p.to_dict() for p in projetos]
        }

        data_str = datetime.now().strftime("%Y_%m_%d-%Hh%M")
        nome_ficheiro = f"backup_{data_str}.json"
        caminho_completo = os.path.join(PASTA_BACKUPS, nome_ficheiro)

        with open(caminho_completo, 'w', encoding='utf-8') as f:
            json.dump(dados_para_guardar, f, ensure_ascii=False, indent=4)

        # Registar log de backup manual
        user_id = int(get_jwt_identity())
        registar_log(
            user_id=user_id,
            acao="GERAR_BACKUP",
            detalhes=f"Gerou manualmente o ficheiro de backup completo '{nome_ficheiro}'."
        )

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


#rota para fazer scan quando quiser
@app.route('/api/admin/forcar-scan', methods=['POST'])
@admin_required
def forcar_scan():
    try:
        gerar_scan_automatico()
        
        # Registar log de scan forçado
        user_id = int(get_jwt_identity())
        registar_log(
            user_id=user_id,
            acao="FORCAR_SCAN",
            detalhes="Executou uma varredura manual forçada em todos os caminhos do sistema."
        )

        return jsonify({
            "sucesso": True,
            "mensagem": "Varredura manual forçada executada com sucesso!"
        }), 200
        
    except Exception as e:
        return jsonify({
            "sucesso": True, 
            "erro": str(e)
        }), 500


#func que o robo vai executar solo
def gerar_backup_automatico():
    with app.app_context():
        caminhos = Caminho.query.all()
        projetos = Projeto.query.all()

        caminhos_com_historico = []
        for c in caminhos:
            c_dict = c.to_dict()
            ultimo_hist = Historico.query.filter_by(caminho_id=c.id).order_by(Historico.data_verificacao.desc()).first()
            if ultimo_hist:
                c_dict['ultimo_historico'] = ultimo_hist.to_dict()
            else:
                c_dict['ultimo_historico'] = None
            caminhos_com_historico.append(c_dict)

        dados = {
            "data_backup": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "caminhos": caminhos_com_historico,
            "projetos": [p.to_dict() for p in projetos]
        }

        data_str = datetime.now().strftime("%Y_%m_%d-%Hh%M")
        nome_ficheiro = f"backup_auto_{data_str}.json"
        caminho_completo = os.path.join(PASTA_BACKUPS, nome_ficheiro)

        with open(caminho_completo, 'w', encoding='utf-8') as f:
            json.dump(dados, f, ensure_ascii=False, indent=4)

        return nome_ficheiro


#func que o robo vai executar para procurar falhas
def gerar_scan_automatico():
    with app.app_context():
        todos_caminhos = Caminho.query.all()
        
        print(f"[{datetime.now()}] Iniciando scan automático de rotina...")
        
        for caminho in todos_caminhos:

            estado, total = executar_scan_caminho(caminho)
            
            if estado not in ["OK", "Acessível", "Ativo"]: 
                alerta_existente = Alerta.query.filter_by(caminho_id=caminho.id, estado_alerta='Por resolver').first()
                
                if not alerta_existente:
                    novo_alerta = Alerta(
                        projeto_id=caminho.projeto_id,
                        caminho_id=caminho.id,
                        tipo_erro=f"Erro de acesso: {estado}",
                        estado_alerta='Por resolver'
                    )
                    db.session.add(novo_alerta)
                    
            # O GATILHO DA INATIVIDADE
            elif caminho.data_ultima_atividade: 
                config = ConfigSistema.query.filter_by(chave='dias_limite_inatividade').first()
                dias_limite = int(config.valor) if config else 4
                
                dias_inativo = (datetime.now() - caminho.data_ultima_atividade).days
                
                if dias_inativo >= dias_limite:
                    alerta_inativo = Alerta.query.filter_by(
                        caminho_id=caminho.id,
                        estado_alerta='Por resolver'
                    ).filter(Alerta.tipo_erro.like('Inatividade%')).first()
                    
                    if not alerta_inativo:
                        novo_alerta_inativo = Alerta(
                            projeto_id=caminho.projeto_id,
                            caminho_id=caminho.id,
                            tipo_erro=f"Inatividade: Sem alterações há {dias_inativo} dias",
                            estado_alerta='Por resolver'
                        )
                        db.session.add(novo_alerta_inativo)
        
        db.session.commit()
        print(f"[{datetime.now()}] Scan automático concluído!")


scheduler = BackgroundScheduler()

# backup da manha
scheduler.add_job(func=gerar_backup_automatico, trigger="cron", hour=9, minute=15)

# backup da tarde
scheduler.add_job(func=gerar_backup_automatico, trigger="cron", hour=17, minute=30)
scheduler.start()

scheduler.add_job(func=gerar_scan_automatico, trigger="interval", hours=2)


#rota do registo
@app.route('/api/register', methods=['POST'])
def register():
    dados = request.get_json()
    username = dados.get('username')
    password = dados.get('password')
    role = dados.get('role', 'user')

    if not username or not password:
        return jsonify({"error": "Preenche o username e a password"}), 400

    #verifica se o user ja existe
    utilizador_existente = User.query.filter_by(username=username).first()
    if utilizador_existente:
        return jsonify({"error": "Esse username já existe!"}), 400

    #encripta a password antes de guardar
    password_criptografada = generate_password_hash(password)

    novo_utilizador = User(username=username, password=password_criptografada, role=role)

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
    access_token = create_access_token(
        identity=str(utilizador.id), 
        additional_claims={"role": utilizador.role}
    )

    return jsonify({
        "message": "login efetuado com sucesso!",
        "access_token": access_token,
        "role": utilizador.role
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


#gestao de alertas
#rota para listar apenas os alertas que precisam de atencao
@app.route('/api/alertas/pendentes', methods=['GET'])
@jwt_required()
def listar_alertas_pendentes():
    #vai a bd bsucar os alertas ainda por resolver
    alertas = Alerta.query.filter_by(estado_alerta='Por resolver').order_by(Alerta.data_hora.desc()).all()
    
    resultado = [alerta.to_dict() for alerta in alertas]
    
    return jsonify({
        "total_pendentes": len(resultado),
        "alertas": resultado
    }), 200


#rota para marcar um alerta como resolvido
@app.route('/api/alertas/<int:id_alerta>/resolver', methods=['PUT'])
@jwt_required()
def resolver_alerta(id_alerta):
    # Procura o alerta pelo ID
    alerta = Alerta.query.get(id_alerta)
    
    if not alerta:
        return jsonify({"erro": "Alerta não encontrado."}), 404
        
    #verifica se ja nao foi resolvido
    if alerta.estado_alerta == 'Resolvido':
        return jsonify({"mensagem": "Este alerta já se encontrava resolvido!"}), 200
        
    #muda o estado e guarda na bd
    alerta.estado_alerta = 'Resolvido'
    db.session.commit()
    
    return jsonify({
        "mensagem": f"Alerta {id_alerta} marcado como resolvido com sucesso!",
        "alerta": alerta.to_dict()
    }), 200


#rota para consultar o historico de alertas resolvidos
@app.route('/api/alertas/historico', methods=['GET'])
@jwt_required()
def listar_alertas_historico():
    # vai a bd buscar os alertas ja resolvidos do mais recente para o mais antigo
    alertas_resolvidos = Alerta.query.filter_by(estado_alerta='Resolvido').order_by(Alerta.data_hora.desc()).all()
    
    resultado = [alerta.to_dict() for alerta in alertas_resolvidos]
    
    return jsonify({
        "total_resolvidos": len(resultado),
        "alertas": resultado
    }), 200


# rota para ler os dados do PC 
@app.route('/api/system', methods=['GET'])
@jwt_required()
def obter_sistema():
    #le as % de uso
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory().percent
    disco = psutil.disk_usage('/').percent
    
    return jsonify({
        "cpu": cpu,
        "ram": ram,
        "disk": disco
    }), 200






#ligar 
if __name__ == '__main__':
    app.run(debug=True)

 