# Tempo Compartilhado 🌤️

Projeto pessoal de portfólio, independente das matérias escolares: uma aplicação full-stack que transforma dados meteorológicos abertos em consulta, acompanhamento e comparação do clima entre cidades. Busque lugares e veja condições atuais e previsões. Favoritos são salvos no banco local, compartilhado pela instância; esta versão é demonstração local e não deve ser hospedada publicamente sem autenticação, isolamento por usuário e proteção CSRF.

## O que demonstra

- Consumo de duas APIs externas: busca geográfica e previsão da [Open-Meteo](https://open-meteo.com/).
- API própria com FastAPI, documentação OpenAPI automática e validação de entradas.
- Comparação simultânea das condições atuais em 2 a 4 cidades e respectivos horários locais.
- Persistência relacional com SQLAlchemy: SQLite local ou PostgreSQL no Compose.
- Interface server-rendered responsiva, busca com debounce, previsão horária/diária e favoritos.
- Testes automatizados isolados dos serviços externos.
- Projeto autoral de portfólio, sem relação com as entregas das disciplinas escolares.

## Executar localmente

Requer Python 3.11 ou superior.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
uvicorn main:app --reload
```

Abra <http://localhost:8000>. A API interativa fica em <http://localhost:8000/docs>. Sem configuração adicional, o SQLite é criado como `clima.db` no diretório do projeto.

## PostgreSQL com Docker Compose

```bash
POSTGRES_PASSWORD='use-uma-senha-local' docker compose up --build
```

A aplicação fica em <http://localhost:8001>. O banco persiste no volume Docker `clima_data`. A senha de exemplo serve apenas para desenvolvimento; defina uma própria em ambientes compartilhados. Docker Compose não foi executado no ambiente de autoria.

## Testes

```bash
pytest -q
```

Os testes usam SQLite temporário e não fazem chamadas de rede. A integração real com as APIs depende de acesso à internet. Instalação de runtime: `python -m pip install -r requirements.txt`.

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | Verificação de saúde |
| GET | `/api/cities/search?q=...` | Busca cidades na Open-Meteo |
| GET | `/api/forecast?latitude=...&longitude=...` | Obtém previsão da coordenada |
| GET | `/api/compare?latitude=...&latitude=...&longitude=...&longitude=...` | Compara condições atuais de 2 a 4 lugares |
| GET | `/api/favorites` | Lista cidades favoritas |
| POST | `/api/favorites` | Salva cidade favorita |
| DELETE | `/api/favorites/{id}` | Remove favorita |

## Transparência

Previsões vêm da Open-Meteo e podem mudar ou ficar indisponíveis. A busca de uma cidade depende da API de geocodificação. Não use o app para decisões de segurança ou emergência; confirme dados em serviços meteorológicos oficiais. Consulte a documentação Open-Meteo para atribuição e termos de uso. Favoritos ficam no banco local configurado e não há contas de usuário; visitantes da mesma instância compartilham essa lista. Não exponha a instância publicamente sem login, isolamento entre usuários, CSRF e limites de uso nas rotas que gravam dados.

## Licença

MIT. Dados meteorológicos mantêm os termos e atribuições de suas fontes originais.
