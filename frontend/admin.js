const token = localStorage.getItem('meu_token_jwt');
const role = localStorage.getItem('user_role');

// Segurança: Se não houver token ou não for admin, expulsa
if (!token || role !== 'admin') {
    alert("Acesso negado! Área exclusiva para administradores.");
    window.location.href = "dashboard.html";
}

async function carregarDadosAdmin() {
    try {
        // --- 1. BUSCAR DADOS DE SOFTWARE ---
        
        // Projetos Ativos[cite: 1]
        const resProjetos = await fetch('http://127.0.0.1:5000/projetos', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (resProjetos.ok) {
            const projetos = await resProjetos.json();
            document.getElementById('metric-projetos').textContent = projetos.length;
        }

        // Alertas Pendentes[cite: 1]
        const resAlertas = await fetch('http://127.0.0.1:5000/api/alertas/pendentes', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (resAlertas.ok) {
            const dadosAlertas = await resAlertas.json();
            document.getElementById('metric-alertas').textContent = dadosAlertas.total_pendentes;
        }

        // --- 2. BUSCAR DADOS DE HARDWARE (PC) ---
        const resSistema = await fetch('http://127.0.0.1:5000/api/system', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (resSistema.ok) {
            const dadosPC = await resSistema.json();
            document.getElementById('metric-cpu').textContent = dadosPC.cpu + '%';
            document.getElementById('metric-ram').textContent = dadosPC.ram + '%';
            document.getElementById('metric-disk').textContent = dadosPC.disk + '%';
        }

    } catch (e) {
        console.error("Erro ao carregar dados do painel admin:", e);
    }
}

// Executar imediatamente e atualizar a cada 5 segundos
carregarDadosAdmin();
setInterval(carregarDadosAdmin, 5000);