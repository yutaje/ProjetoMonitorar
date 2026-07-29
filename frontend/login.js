document.getElementById('form-login').addEventListener('submit', async function(event) {
    event.preventDefault(); // Impede a página de recarregar ao clicar no botão

    // Vai buscar os dados dos inputs
    const usernameInput = document.getElementById('username').value;
    const passwordInput = document.getElementById('password').value;
    const mensagemErro = document.getElementById('mensagem-erro');

    // Esconde o erro antes de tentar novamente
    mensagemErro.classList.add('d-none');

    try {
        // Envia os dados para o teu Flask (Backend)
        const resposta = await fetch('http://127.0.0.1:5000/api/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                username: usernameInput,
                password: passwordInput
            })
        });

        const dados = await resposta.json();

        if (resposta.ok) {
            // SUCESSO! Guarda o token no navegador
            localStorage.setItem('meu_token_jwt', dados.access_token);
            localStorage.setItem('user_role', dados.role);
            
            localStorage.setItem('username', usernameInput);

            alert("Login com sucesso, patrão! O token foi guardado.");
            window.location.href = "dashboard.html"; 
        } else {
            // ERRO DA API (ex: Password Errada)
            mensagemErro.textContent = dados.error || "Erro ao fazer login.";
            mensagemErro.classList.remove('d-none');
        }

    } catch (erro) {
        // ERRO DE REDE (ex: Flask está desligado)
        mensagemErro.textContent = "Erro de ligação. O Backend (Flask) está a correr?";
        mensagemErro.classList.remove('d-none');
    }
});