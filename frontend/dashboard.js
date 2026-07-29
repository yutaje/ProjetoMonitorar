//verifica a sec ao abrir a pagina
const token = localStorage.getItem('meu_token_jwt');

// senao houver token redireciona para a login page
if (!token) {
    alert("Acesso negado! Tens de fazer login primeiro.");
    window.location.href = "login.html";
}

//logout button
document.getElementById('btn-logout').addEventListener('click', function() {
    localStorage.removeItem('meu_token_jwt');
    localStorage.removeItem('user_role');
    localStorage.removeItem('username'); 
    
    //manda o user de novo para a login page
    window.location.href = "login.html";
});

//mostra o user na navbar
const nomeUtilizador = localStorage.getItem('username');

//se houver um nome guardado, atualiza
if (nomeUtilizador) {
    document.getElementById('titulo-navbar').textContent = `🖥️ Dashboard (${nomeUtilizador})`;
}

//vai buscar dados reais a API
async function carregarDadosDashboard() {
    try {
        //vai buscar os projs
        const resProjetos = await fetch('http://127.0.0.1:5000/projetos', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}` // O teu token a abrir as portas!
            }
        });

        if (resProjetos.ok) {
            const projetos = await resProjetos.json();
            document.getElementById('metric-projetos').textContent = projetos.length;
        }

        // vai buscar os alertas pendentes
        const resAlertas = await fetch('http://127.0.0.1:5000/api/alertas/pendentes', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            }
        });

        if (resAlertas.ok) {
            const dadosAlertas = await resAlertas.json();
            // Injeta o número de alertas pendentes no HTML
            document.getElementById('metric-alertas').textContent = dadosAlertas.total_pendentes;
        }

        // mostra a role do user
        const userRole = localStorage.getItem('user_role');
        if (userRole) {
            document.getElementById('metric-role').textContent = userRole.charAt(0).toUpperCase() + userRole.slice(1);
        }

    } catch (erro) {
        console.error("Erro ao contactar o servidor:", erro);
    }
}

// Correr a função mal o Dashboard abre para não ficarem a zero
carregarDadosDashboard();

// atualiza os dados de 5 em 5 segundos
setInterval(carregarDadosDashboard, 5000);