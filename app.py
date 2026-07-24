from flask import Flask

#criar API
app = Flask(__name__)

#1 endpoint
@app.route('/')
def pagina_principal():
    return 'funcional'

#ligar 
if __name__ == '__main__':
    app.run(debug=True)

