const token = localStorage.getItem('meu_token_jwt');

if (!token) {
    alert("Acesso negado! Tens de fazer login primeiro.");
    window.location.href = "login.html";
}

// Botão de Logout
document.getElementById('btn-logout').addEventListener('click', function() {
    localStorage.removeItem('meu_token_jwt');
    localStorage.removeItem('user_role');
    localStorage.removeItem('username'); 
    window.location.href = "login.html";
});

// Mostra o user na navbar entre parênteses
const nomeUtilizador = localStorage.getItem('username');
if (nomeUtilizador) {
    document.getElementById('titulo-navbar').textContent = `🖥️ Dashboard (${nomeUtilizador})`;
}

// Função para atualizar as métricas e dados de hardware de forma limpa
async function atualizarMetricasDashboard() {
    try {
        // 1. Contagem de Projetos Ativos
        const resProjetos = await fetch('http://127.0.0.1:5000/projetos', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (resProjetos.ok) {
            const projetos = await resProjetos.json();
            document.getElementById('metric-projetos').textContent = projetos.length;
        }

        // 2. Alertas Pendentes
        const resAlertas = await fetch('http://127.0.0.1:5000/api/alertas/pendentes', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (resAlertas.ok) {
            const dadosAlertas = await resAlertas.json();
            document.getElementById('metric-alertas').textContent = dadosAlertas.total_pendentes;
        }

        // 3. Recursos da Máquina (CPU, RAM, Disco)
        const resSistema = await fetch('http://127.0.0.1:5000/api/system', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (resSistema.ok) {
            const dadosPC = await resSistema.json();
            document.getElementById('metric-cpu').textContent = dadosPC.cpu + '%';
            document.getElementById('metric-ram').textContent = dadosPC.ram + '%';
            document.getElementById('metric-disk').textContent = dadosPC.disk + '%';
        }
    } catch (erro) {
        console.error("Erro ao atualizar métricas:", erro);
    }
}

// Mostrar role do utilizador e botão de admin se aplicável
const userRole = localStorage.getItem('user_role');
if (userRole) {
    document.getElementById('metric-role').textContent = userRole.charAt(0).toUpperCase() + userRole.slice(1);
    const btnAdmin = document.getElementById('btn-admin');
    if (userRole === 'admin' && btnAdmin) {
        btnAdmin.classList.remove('d-none');
    }
}

// Executa na abertura e atualiza a cada 2 segundos
atualizarMetricasDashboard();
setInterval(atualizarMetricasDashboard, 2000);