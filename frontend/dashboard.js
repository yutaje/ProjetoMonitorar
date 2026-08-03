const token = localStorage.getItem('meu_token_jwt') || localStorage.getItem('token') || localStorage.getItem('access_token');

if (!token) {
    alert("Acesso negado! Tens de fazer login primeiro.");
    window.location.href = "login.html";
}

// ==========================================
// CONFIGURAÇÕES GERAIS (User, Admin, Logout)
// ==========================================
const btnLogout = document.getElementById('btn-logout');
if (btnLogout) {
    btnLogout.addEventListener('click', function() {
        localStorage.clear();
        window.location.href = "login.html";
    });
}

const nomeUtilizador = localStorage.getItem('username');
if (nomeUtilizador) {
    const tituloNavbar = document.getElementById('titulo-navbar');
    if (tituloNavbar) tituloNavbar.textContent = `🖥️ Dashboard (${nomeUtilizador})`;
}

const userRole = localStorage.getItem('user_role');
if (userRole) {
    const metricRole = document.getElementById('metric-role');
    if (metricRole) metricRole.textContent = userRole.charAt(0).toUpperCase() + userRole.slice(1);
    
    const btnAdmin = document.getElementById('btn-admin');
    if (userRole === 'admin' && btnAdmin) {
        btnAdmin.classList.remove('d-none');
    }
}

// ==========================================
// ATUALIZAÇÃO DAS MÉTRICAS DO SISTEMA
// ==========================================
async function atualizarMetricasDashboard() {
    try {
        const resProjetos = await fetch('http://127.0.0.1:5000/projetos', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (resProjetos.ok) {
            const projetos = await resProjetos.json();
            document.getElementById('metric-projetos').textContent = projetos.length;
        }

        const resAlertas = await fetch('http://127.0.0.1:5000/api/alertas/pendentes', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (resAlertas.ok) {
            const dadosAlertas = await resAlertas.json();
            document.getElementById('metric-alertas').textContent = dadosAlertas.total_pendentes !== undefined ? dadosAlertas.total_pendentes : 0;
        }

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

// ==========================================
// FUNÇÕES DE ABERTURA E CÓPIA SEGURA
// ==========================================
function abrirPastaDoBotao(botao) {
    let caminho = botao.getAttribute('data-caminho');
    if (!caminho) return;
    caminho = caminho.replace(/\\/g, '/');
    const caminhoCodificado = encodeURI(caminho);
    const url = `monitorapp://${caminhoCodificado}`;
    
    let iframe = document.getElementById('hidden-protocol-frame');
    if (!iframe) {
        iframe = document.createElement('iframe');
        iframe.id = 'hidden-protocol-frame';
        iframe.style.display = 'none';
        document.body.appendChild(iframe);
    }
    iframe.src = url;
}

window.copiarCaminhoModal = async function(caminho, btn) {
    try {
        await navigator.clipboard.writeText(caminho);
        const textoOriginal = btn.innerHTML;
        btn.innerHTML = '✅ Copiado!';
        btn.classList.replace('btn-outline-secondary', 'btn-success');
        btn.classList.add('text-white');
        
        setTimeout(() => {
            btn.innerHTML = textoOriginal;
            btn.classList.replace('btn-success', 'btn-outline-secondary');
            btn.classList.remove('text-white');
        }, 2000);
    } catch (err) {
        console.error('Falha ao copiar: ', err);
        alert('O teu browser bloqueou a cópia. Tenta dar permissões.');
    }
};

// ==========================================
// LÓGICA DE PESQUISA HÍBRIDA (LIVE + MODAL)
// ==========================================
const formPesquisa = document.getElementById('formPesquisaGlobal');
const inputPesquisa = document.getElementById('inputPesquisa');
const dropdownResultados = document.getElementById('dropdownResultados');
let timeoutPesquisa;

if (inputPesquisa && formPesquisa) {
    inputPesquisa.addEventListener('input', function(e) {
        let termo = this.value.trim();
        
        if (termo === "") {
            dropdownResultados.style.display = 'none';
            dropdownResultados.innerHTML = '';
            return;
        }

        clearTimeout(timeoutPesquisa);
        timeoutPesquisa = setTimeout(() => {
            fetch(`http://127.0.0.1:5000/api/pesquisa-global?q=${encodeURIComponent(termo)}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            })
            .then(res => res.json())
            .then(data => {
                dropdownResultados.innerHTML = ''; 
                if(data.total === 0) {
                    dropdownResultados.innerHTML = `<span class="dropdown-item text-muted">Nenhum resultado para "${data.termo}".</span>`;
                } else {
                    data.resultados.forEach(proj => {
                        const dataCaminho = proj.caminho.replace(/\\/g, '\\\\').replace(/"/g, '&quot;');
                        dropdownResultados.innerHTML += `
                            <div class="dropdown-item border-bottom py-2" style="cursor: pointer;" onclick="abrirPastaDoBotao(this)" data-caminho="${dataCaminho}">
                                <div class="fw-bold text-primary">${proj.nome}</div>
                                <small class="text-muted text-wrap" style="font-size: 0.75rem;">${proj.caminho}</small>
                            </div>
                        `;
                    });
                }
                dropdownResultados.style.display = 'block'; 
            }).catch(err => console.error("Erro na pesquisa live:", err));
        }, 300); 
    });

    document.addEventListener('click', function(event) {
        if (!formPesquisa.contains(event.target)) {
            dropdownResultados.style.display = 'none';
        }
    });

    inputPesquisa.addEventListener('focus', function() {
        if (this.value.trim() !== "" && dropdownResultados.innerHTML !== "") {
            dropdownResultados.style.display = 'block';
        }
    });

    formPesquisa.addEventListener('submit', function(e) {
        e.preventDefault(); 
        let termo = inputPesquisa.value.trim();
        
        if (termo === "") return;

        dropdownResultados.style.display = 'none';

        fetch(`http://127.0.0.1:5000/api/pesquisa-global?q=${encodeURIComponent(termo)}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        })
        .then(res => res.json())
        .then(data => {
            const listaModal = document.getElementById('lista-resultados-pesquisa');
            if (listaModal) {
                listaModal.innerHTML = '';
                
                if(data.total === 0) {
                    listaModal.innerHTML = `<div class="p-4 text-center text-muted fw-bold">Nenhum resultado encontrado para "${data.termo}".</div>`;
                } else {
                    data.resultados.forEach(proj => {
                        const caminhoEscapado = proj.caminho.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                        const dataCaminho = proj.caminho.replace(/\\/g, '\\\\').replace(/"/g, '&quot;');
                        
                        listaModal.innerHTML += `
                            <div class="list-group-item p-3">
                                <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">
                                    <div>
                                        <h5 class="mb-1 text-primary fw-bold">📁 ${proj.nome}</h5>
                                        <small class="text-muted text-break">${proj.caminho}</small>
                                    </div>
                                    <div class="d-flex gap-2">
                                        <button type="button" class="btn btn-outline-secondary text-nowrap fw-bold" onclick="copiarCaminhoModal('${caminhoEscapado}', this)">
                                            📋 Copiar
                                        </button>
                                        <button type="button" class="btn btn-outline-info text-nowrap fw-bold" onclick="abrirPastaDoBotao(this)" data-caminho="${dataCaminho}">
                                            📂 Abrir
                                        </button>
                                    </div>
                                </div>
                            </div>
                        `;
                    });
                }
                const modalEl = document.getElementById('modalResultadosPesquisa');
                if (modalEl) {
                    const modalResultados = new bootstrap.Modal(modalEl);
                    modalResultados.show();
                }
            }
        })
        .catch(err => console.error("Erro na pesquisa do modal:", err));
    });
}

// ==========================================
// EXECUÇÃO INICIAL E LOOP
// ==========================================
atualizarMetricasDashboard();
setInterval(atualizarMetricasDashboard, 2000);