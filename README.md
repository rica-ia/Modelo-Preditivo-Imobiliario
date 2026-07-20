# Modelo Preditivo Imobiliário
## Real Estate Predictive Model — Precificação de imóveis em King County

<p align="center">
  <strong>Pipeline reprodutível de regressão para estimar preços residenciais, da auditoria dos dados ao modelo v1, com validação agrupada, diagnóstico de generalização e interpretação de negócio.</strong>
</p>

<p align="center">
  <img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-1e3a8a?style=for-the-badge&logo=python&logoColor=white">
  <img alt="Pandas 2.2.3" src="https://img.shields.io/badge/Pandas-2.2.3-2563eb?style=for-the-badge&logo=pandas&logoColor=white">
  <img alt="scikit-learn 1.8.0" src="https://img.shields.io/badge/scikit--learn-1.8.0-f59e0b?style=for-the-badge&logo=scikitlearn&logoColor=white">
  <img alt="Google Colab" src="https://img.shields.io/badge/Ambiente-Google%20Colab-f9ab00?style=for-the-badge&logo=googlecolab&logoColor=white">
  <img alt="Modelo v1" src="https://img.shields.io/badge/Modelo-v1-16a34a?style=for-the-badge">
  <img alt="Licença MIT" src="https://img.shields.io/badge/Licen%C3%A7a-MIT-475569?style=for-the-badge">
</p>

<p align="center">
  <a href="https://colab.research.google.com/github/rica-ia/Modelo-Preditivo-Imobiliario/blob/main/notebooks/modelo_preditivo_imobiliario.ipynb">
    <img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Abrir no Google Colab">
  </a>
</p>

---

## 1. Identificação

| Campo | Informação |
|---|---|
| Curso | Desenvolvimento em IA para Análise Preditiva |
| Projeto | Projeto Avaliativo Final — Módulo I |
| Professor | Maurício Costa Cordeiro |
| Aluno | Ricardo Pasquali dos Reis |
| Dataset | King County House Sales — Opção A |
| Ambiente de desenvolvimento | Google Colab |
| Problema | Regressão supervisionada |
| Variável-alvo | `price`, preço de venda em dólares |
| Modelo entregue | HistGradientBoosting com alvo logarítmico e correção de retransformação — v1 |
| Repositório | [rica-ia/Modelo-Preditivo-Imobiliario](https://github.com/rica-ia/Modelo-Preditivo-Imobiliario/) |

---

## 2. Visão geral

O projeto estima uma referência inicial para o preço de venda de imóveis residenciais de King County, no estado de Washington. A solução percorre as seis fases da proposta avaliativa: análise exploratória, limpeza, engenharia de atributos, preparação, modelagem e avaliação com versionamento.

Desenvolvimento, execução e versionamento são realizados no Google Colab com **um único notebook**. A versão acadêmica está organizada em preparação, seis fases avaliativas explícitas e conclusão. Durante a construção, comandos de checkpoint, branch e merge ocupam células temporárias; antes de cada registro, somente a versão sanitizada é indexada. A `develop` concentra as fases, enquanto `experiment/modelos` isola a comparação dos algoritmos e só retorna por merge após a validação. README e módulos permanecem como arquivos independentes no repositório.

A média do treino fornece a referência ingênua, e a Regressão Linear funciona como baseline aprendido e interpretável. Dois modelos não lineares ampliam a comparação: HistGradientBoosting no preço original e HistGradientBoosting treinado em `log1p(price)`, com correção de retransformação aprendida somente no treino. O campeão é escolhido pelo menor RMSE médio em validação cruzada agrupada; o teste permanece isolado até essa decisão.

O resultado apoia triagem, priorização e definição de faixa inicial. Ele não substitui vistoria, análise de comparáveis ou laudo, sobretudo no segmento de alto padrão.

---

## 3. Problema preditivo

> **Objetivo:** prever `price`, uma variável numérica contínua expressa em dólares, a partir de características físicas, temporais e geográficas disponíveis antes da venda.

Uma estimativa acompanhada de erro conhecido pode apoiar:

- triagem e priorização do portfólio;
- definição de uma faixa inicial de anúncio;
- identificação de preços muito afastados do padrão observado;
- encaminhamento dos casos de maior risco para avaliação especializada.

O modelo estima um preço provável condicionado à base histórica; não determina valor justo e não garante uma margem individual de erro.

---

## 4. Dataset e qualidade inicial

| Item | Resultado |
|---|---:|
| Registros | 21.613 vendas realizadas em 2014–2015 |
| Colunas | 21 |
| Faixa do alvo | US$ 75 mil a US$ 7,7 milhões |
| Mediana do alvo | US$ 450 mil |
| Duplicatas integrais | 0 |
| Imóveis com revenda | 176 |
| Registros adicionais de revenda | 177 |
| Valores ausentes | 2 em `sqft_above` |
| Incompatibilidades entre quartos e área | 1 |
| Vendas anteriores ao ano de construção registrado | 12 |

IDs repetidos foram preservados porque representam novos eventos de venda, com datas e preços próprios. Para impedir que duas vendas do mesmo imóvel contaminem a avaliação, todas as divisões de treino, validação e teste são agrupadas por `id`.

A cópia bruta utilizada pelo notebook está disponível em [`kc_house_data.csv`](https://drive.google.com/file/d/1XMw1aKYqfFA13AbOzd9zRElv216bCxqZ/view?usp=sharing). A Célula 0 faz o download anônimo e aceita o arquivo somente quando o SHA-256 corresponde a `aa501a2b18e0d0a288a0fdeb043b2c89d6c7e2ead1f9588165537d4e4e12b9df`.

---

## 5. Resultado executivo

| Indicador do campeão no teste isolado | Resultado |
|---|---:|
| Treino / teste | 17.289 / 4.324 registros |
| IDs presentes nos dois conjuntos | **0** |
| MAE | **US$ 64.720** |
| MSE | US$ 14.577.071.521 |
| RMSE | **US$ 120.736** |
| R² | **0,8956** |
| MAPE | **11,95%** |
| Erros de até US$ 50 mil | 60,4% |
| Erros de até US$ 100 mil | 82,8% |

O MAE equivale a 14,4% da mediana de US$ 450 mil do teste. O modelo explica 89,6% da variação observada no holdout, mas o quartil de maior preço apresenta MAE de US$ 131,4 mil. A qualidade média é adequada para apoio inicial; a cauda de alto valor exige análise especializada.

---

## 6. Estrutura do projeto

<p align="center">
  <img src="assets/estrutura_projeto.svg" alt="Estrutura visual do projeto Modelo Preditivo Imobiliário" width="100%">
</p>

```text
Modelo-Preditivo-Imobiliario/
├── assets/
│   ├── estrutura_projeto.svg
│   ├── fluxo_branches.svg
│   └── pipeline_preditivo.svg
├── data/
│   ├── raw/kc_house_data.csv
│   ├── processed/kc_house_processed.csv
│   ├── final/kc_house_final.csv
│   └── geospatial/king_county.geojson
├── models/v1/
│   ├── modelo_regressao_v1.pkl
│   └── metricas_v1.json
├── notebooks/
│   └── modelo_preditivo_imobiliario.ipynb
├── outputs/
│   ├── figures/
│   ├── maps/
│   │   ├── painel_geoespacial.html
│   │   ├── regioes_h3_valor_m2.csv
│   │   └── resumo_mapa_valor_m2.json
│   ├── correlacoes_pearson_spearman.csv
│   ├── cv_modelos_folds.csv
│   ├── cv_modelos_resumo.csv
│   ├── diagnostico_distribuicao_alvo.csv
│   ├── diagnostico_generalizacao.csv
│   ├── erros_por_faixa_preco.csv
│   ├── importancia_permutacao.csv
│   ├── metricas_modelos.csv
│   ├── relatorio_qualidade_dados.json
│   ├── resumo_residuos.json
│   ├── vitorias_por_fold.csv
│   ├── vif_antes.csv
│   └── vif_depois.csv
├── src/
│   ├── config.py
│   ├── data.py
│   ├── features.py
│   ├── modeling.py
│   ├── plots.py
│   ├── spatial.py
│   └── templates/painel_geoespacial.html
├── environment_info.json
├── requirements.txt
├── LICENSE
└── README.md
```

---

## 7. Arquivos principais e downloads

O `README.md` é o único arquivo em Markdown. Notebook, módulos, dados, modelo e resultados preservam seus formatos técnicos próprios; guias de autenticação, checkpoints e auditoria ficam fora da versão pública. **Cada nome abaixo é um hyperlink direto para abrir ou baixar o respectivo arquivo.**

### Execução, documentação e arquitetura

| Arquivo | Finalidade |
|---|---|
| [`README.md`](README.md?raw=1) | documentação integral do projeto |
| [`notebooks/modelo_preditivo_imobiliario.ipynb`](notebooks/modelo_preditivo_imobiliario.ipynb?raw=1) | notebook acadêmico validado integralmente, com problema declarado, seis fases explícitas e conclusão |
| [`requirements.txt`](requirements.txt?raw=1) | versões fixadas das dependências |
| [`environment_info.json`](environment_info.json?raw=1) | ambiente efetivamente utilizado |
| [`LICENSE`](LICENSE?raw=1) | licença MIT |
| [`assets/estrutura_projeto.svg`](assets/estrutura_projeto.svg?raw=1) | arquitetura de pastas e artefatos |
| [`assets/pipeline_preditivo.svg`](assets/pipeline_preditivo.svg?raw=1) | fluxo analítico da base bruta ao modelo v1 |
| [`assets/fluxo_branches.svg`](assets/fluxo_branches.svg?raw=1) | caminho de `main`, `develop` e `experiment/modelos` |

### Código-fonte e template

| Arquivo | Finalidade |
|---|---|
| [`src/__init__.py`](src/__init__.py?raw=1) | inicialização do pacote local |
| [`src/config.py`](src/config.py?raw=1) | caminhos, sementes, features e parâmetros |
| [`src/data.py`](src/data.py?raw=1) | leitura e validação da base |
| [`src/features.py`](src/features.py?raw=1) | limpeza, atributos, VIF e preparação dos preditores |
| [`src/modeling.py`](src/modeling.py?raw=1) | pipelines, validação, métricas e retransformação |
| [`src/plots.py`](src/plots.py?raw=1) | gráficos exploratórios e diagnósticos do modelo |
| [`src/spatial.py`](src/spatial.py?raw=1) | agregação H3 e geração do painel geoespacial |
| [`src/templates/painel_geoespacial.html`](src/templates/painel_geoespacial.html?raw=1) | template responsivo do painel Leaflet |

### Dados e modelo versionado

| Arquivo | Finalidade |
|---|---|
| [`data/raw/kc_house_data.csv`](data/raw/kc_house_data.csv?raw=1) | base original preservada |
| [`data/processed/kc_house_processed.csv`](data/processed/kc_house_processed.csv?raw=1) | base limpa e enriquecida |
| [`data/final/kc_house_final.csv`](data/final/kc_house_final.csv?raw=1) | 19 preditores e alvo utilizados na modelagem |
| [`data/geospatial/king_county.geojson`](data/geospatial/king_county.geojson?raw=1) | limite territorial oficial empregado no painel |
| [`models/v1/modelo_regressao_v1.pkl`](models/v1/modelo_regressao_v1.pkl?raw=1) | preprocessamento e modelo final retreinados na base completa |
| [`models/v1/metricas_v1.json`](models/v1/metricas_v1.json?raw=1) | configuração, validação cruzada e métricas do teste |

### Resultados numéricos

| Arquivo | Evidência preservada |
|---|---|
| [`outputs/correlacoes_pearson_spearman.csv`](outputs/correlacoes_pearson_spearman.csv?raw=1) | associações lineares e monotônicas com o alvo |
| [`outputs/diagnostico_distribuicao_alvo.csv`](outputs/diagnostico_distribuicao_alvo.csv?raw=1) | assimetria e curtose do preço antes e depois de `log1p` |
| [`outputs/vif_antes.csv`](outputs/vif_antes.csv?raw=1) | multicolinearidade antes da seleção |
| [`outputs/vif_depois.csv`](outputs/vif_depois.csv?raw=1) | multicolinearidade após a retirada de redundâncias |
| [`outputs/cv_modelos_folds.csv`](outputs/cv_modelos_folds.csv?raw=1) | desempenho por candidato e fold agrupado |
| [`outputs/cv_modelos_resumo.csv`](outputs/cv_modelos_resumo.csv?raw=1) | médias e desvios usados na escolha do campeão |
| [`outputs/vitorias_por_fold.csv`](outputs/vitorias_por_fold.csv?raw=1) | modelo de menor RMSE em cada fold agrupado |
| [`outputs/metricas_modelos.csv`](outputs/metricas_modelos.csv?raw=1) | métricas de treino e teste dos quatro candidatos |
| [`outputs/diagnostico_generalizacao.csv`](outputs/diagnostico_generalizacao.csv?raw=1) | gaps de erro e R² fora da amostra |
| [`outputs/erros_por_faixa_preco.csv`](outputs/erros_por_faixa_preco.csv?raw=1) | risco segmentado por quartil de preço |
| [`outputs/resumo_residuos.json`](outputs/resumo_residuos.json?raw=1) | centro, dispersão e proporções de erro absoluto |
| [`outputs/importancia_permutacao.csv`](outputs/importancia_permutacao.csv?raw=1) | dependência preditiva das variáveis no teste |
| [`outputs/relatorio_qualidade_dados.json`](outputs/relatorio_qualidade_dados.json?raw=1) | auditoria e tratamentos de qualidade |

### Gráficos e painel geoespacial

| Arquivo | Conteúdo |
|---|---|
| [`outputs/figures/01_distribuicao_preco.png`](outputs/figures/01_distribuicao_preco.png?raw=1) | preço original e após `log1p` |
| [`outputs/figures/02_relacoes_preco.png`](outputs/figures/02_relacoes_preco.png?raw=1) | área construída e padrão versus preço |
| [`outputs/figures/03_correlacao_pearson.png`](outputs/figures/03_correlacao_pearson.png?raw=1) | mapa de correlação numérica |
| [`outputs/figures/04_boxplots_outliers.png`](outputs/figures/04_boxplots_outliers.png?raw=1) | diagnóstico de extremos |
| [`outputs/figures/05_validacao_cruzada_modelos.png`](outputs/figures/05_validacao_cruzada_modelos.png?raw=1) | estabilidade fold a fold e redução do RMSE frente à média do treino |
| [`outputs/figures/06_generalizacao_modelos.png`](outputs/figures/06_generalizacao_modelos.png?raw=1) | RMSE e R² de treino versus teste |
| [`outputs/figures/07_real_vs_previsto.png`](outputs/figures/07_real_vs_previsto.png?raw=1) | preços reais e previstos no holdout |
| [`outputs/figures/08_residuos.png`](outputs/figures/08_residuos.png?raw=1) | distribuição e padrão dos resíduos |
| [`outputs/figures/09_importancia_permutacao.png`](outputs/figures/09_importancia_permutacao.png?raw=1) | importância por permutação no teste |
| [`outputs/maps/painel_geoespacial.html`](outputs/maps/painel_geoespacial.html?raw=1) | painel com H3, vendas, filtros, ranking e ajuste de tela |
| [`outputs/maps/regioes_h3_valor_m2.csv`](outputs/maps/regioes_h3_valor_m2.csv?raw=1) | estatísticas e cobertura das 290 células exibidas |
| [`outputs/maps/resumo_mapa_valor_m2.json`](outputs/maps/resumo_mapa_valor_m2.json?raw=1) | resolução, cobertura, escala e limiar espacial |

---

## 8. Pipeline preditivo e fluxo de branches

### Encadeamento analítico

<p align="center">
  <img src="assets/pipeline_preditivo.svg" alt="Pipeline preditivo da base bruta ao modelo v1" width="100%">
</p>

O holdout é separado por `id` antes da comparação dos algoritmos. O `GroupKFold` opera somente no treino e o teste isolado é consultado após a escolha do campeão.

### Caminho específico da branch experimental

<p align="center">
  <img src="assets/fluxo_branches.svg" alt="Fluxo entre main, develop e experiment/modelos" width="100%">
</p>

O caminho efetivo é `main` → `develop` → `experiment/modelos` → `develop` → `main`. A branch experimental nasce da `develop` após a preparação, compara o baseline ingênuo e os três modelos aprendidos e retorna por `merge --no-ff` somente porque o HistGradientBoosting Log venceu os cinco folds. Um resultado insuficiente permaneceria isolado, sem integração funcional à entrega.

| Momento do pipeline | Células | Branch ativa | Regra de integração |
|---|:---:|---|---|
| Preparação e Fases 1–4 | preparação até Fase 4 | `develop` | checkpoints de ambiente, EDA, limpeza, atributos e preparação |
| Comparação dos candidatos | Fase 5 | `experiment/modelos` | branch criada a partir de `develop`; nenhum acesso ao holdout |
| Retorno do experimento | — | `experiment/modelos` → `develop` | `merge --no-ff` apenas se o vencedor superar o baseline nos cinco folds |
| Avaliação e modelo v1 | Fase 6 e conclusão | `develop` | teste isolado, diagnóstico, artefatos e documentação |
| Consolidação da entrega | notebook sanitizado | `develop` → `main` | benchmark integral, auditoria e `merge --no-ff` final |

---

## 9. Cobertura dos requisitos avaliativos

| Requisito | Evidência verificável | Situação |
|---|---|:---:|
| Problema preditivo declarado | abertura do notebook identifica `price`, contexto imobiliário e relevância de negócio | Atendido |
| EDA e estatística descritiva | dimensões, tipos, `.describe()`, assimetria, Pearson, Spearman e mais de três visualizações | Atendido |
| Limpeza fundamentada | auditoria de duplicatas, imputação pela mediana, boxplots e regra composta para a anomalia de quartos | Atendido |
| Engenharia de atributos | idade, reforma, porão, tempo, log de área e preço por m² restrito à análise | Atendido |
| Preparação segura | VIF, one-hot de `zipcode`, escala dentro do pipeline e separação agrupada por `id` | Atendido |
| Modelagem comparativa | média do treino, Regressão Linear e duas alternativas não lineares avaliadas com `GroupKFold` | Atendido |
| Avaliação e interpretação | MAE, MSE, RMSE, R², MAPE, generalização, resíduos, risco por faixa e veredito de negócio | Atendido |
| Versionamento do modelo | pipeline v1 recarregável, métricas preservadas e ambiente registrado | Atendido |
| Estrutura e reprodutibilidade | notebook, `src/`, `data/`, `outputs/`, `models/`, `requirements.txt`, `develop` e `experiment/modelos` | Atendido |

### Encadeamento das seis fases

| Fase | Células | Evidências produzidas | Decisão central |
|---|---:|---|---|
| 1 — EDA | seções 2.1–2.3 | dimensões, tipos, `.describe()`, assimetria, relações com o alvo, Pearson, Spearman e painel geoespacial | reconhecer a cauda de preços, a concentração espacial e os limites de representatividade |
| 2 — Limpeza | seção 3 | duplicatas, revendas, ausências, boxplots e regra composta de anomalia | preservar extremos plausíveis e corrigir apenas o registro incompatível de 33 quartos |
| 3 — Engenharia de atributos | seção 4 | idade, reforma, porão, mês, ano, área e log do terreno | limitar idade a zero em 12 casos e manter `preco_por_m2` fora do modelo |
| 4 — Preparação | seção 5 | VIF antes/depois, `GroupShuffleSplit`, one-hot e escala | reduzir redundância, manter revendas juntas e ajustar transformações somente no treino |
| 5 — Modelagem | seção 6 | referência pela média, Linear, boosting original e boosting log; `GroupKFold` em cinco folds | selecionar o campeão sem consultar o teste |
| 6 — Avaliação | seção 7 | MAE, MSE, RMSE, R², MAPE, gaps, resíduos, quartis, importância e modelo v1 | recomendar uso assistido e cautela no alto padrão |

---

## 10. Decisões técnicas orientadas pelos dados

| Achado | Tratamento | Justificativa |
|---|---|---|
| Nenhuma duplicata integral | nenhuma linha removida | não havia redundância amostral |
| IDs repetidos | revendas mantidas e divisão agrupada por `id` | eventos distintos são válidos, mas não podem atravessar treino e teste |
| 2 nulos em `sqft_above` | mediana de 1.560 ft² | a mediana reduz influência da assimetria; a coluna é depois retirada por redundância |
| 11 quartos em 3.000 ft² | registro preservado | raro, porém plausível: 272,7 ft² por quarto |
| 33 quartos em 1.620 ft² | substituição por 3 quartos | menos de 100 ft² por quarto; mediana de 2.328 imóveis comparáveis igual a 3 |
| 12 vendas com ano de construção posterior | `idade_imovel.clip(lower=0)` | representa venda na planta ou durante a conclusão sem produzir idade negativa |
| Mansões e terrenos extremos | valores preservados | raridade não equivale a erro cadastral |
| `sqft_living = sqft_above + sqft_basement` | remoção de `sqft_above` | elimina multicolinearidade estrutural e preserva área total e porão |
| `log_sqft_lot15` redundante | variável removida | reduz redundância com `log_sqft_lot` |
| `zipcode` nominal | one-hot dentro do pipeline | evita impor ordem e ignora categorias futuras desconhecidas |
| `preco_por_m2` deriva do alvo | uso exclusivo na EDA | impede vazamento direto de `price` |
| Densidade espacial desigual | H3 r7, mediana e mínimo de 20 vendas por célula | evita atribuir destaque a regiões sustentadas por poucas observações |

O VIF máximo cai de aproximadamente 199 mil para 6,57 após a retirada das redundâncias estruturais.

---

## 11. Seleção do modelo

O holdout de 20% é separado por `id` antes da escolha. Nos 80% restantes, `GroupKFold` executa cinco folds com o mesmo preprocessamento para todos os candidatos. O critério fixado previamente é o menor RMSE médio; MAE, R² e MAPE funcionam como verificações de consistência.

| Modelo | MAE médio | RMSE médio | R² médio | MAPE médio |
|---|---:|---:|---:|---:|
| **HistGradientBoosting Log** | **US$ 63.780** | **US$ 119.154** | **0,8933** | **11,99%** |
| HistGradientBoosting | US$ 68.232 | US$ 126.588 | 0,8796 | 13,03% |
| Regressão Linear | US$ 95.806 | US$ 160.244 | 0,8074 | 19,71% |
| Baseline pela média | US$ 232.912 | US$ 365.399 | −0,0001 | 53,39% |

A variante logarítmica vence nos cinco folds, reduz o MAE em **72,6%** e o RMSE em **67,4%** frente ao palpite pela média. A escolha também é coerente com a EDA: `log1p` reduz a assimetria do alvo de **4,024 para 0,428**, e o boosting preserva a capacidade de representar interações e relações não lineares. A correção de retransformação é calculada exclusivamente nos dados de treino de cada ajuste; o holdout não participa dessa decisão.

---

## 12. Treino, teste e generalização

| Modelo | Conjunto | MAE | RMSE | R² | MAPE |
|---|---|---:|---:|---:|---:|
| Baseline pela média | Treino | US$ 232.901 | US$ 365.436 | 0,0000 | 53,39% |
| Baseline pela média | Teste | US$ 236.441 | US$ 373.780 | −0,0003 | 53,30% |
| Regressão Linear | Treino | US$ 95.232 | US$ 159.244 | 0,8101 | 19,60% |
| Regressão Linear | Teste | US$ 95.933 | US$ 161.596 | 0,8130 | 19,67% |
| HistGradientBoosting | Treino | US$ 61.870 | US$ 106.398 | 0,9152 | 12,30% |
| HistGradientBoosting | Teste | US$ 69.097 | US$ 125.599 | 0,8871 | 13,06% |
| **HistGradientBoosting Log** | **Treino** | **US$ 57.189** | **US$ 105.052** | **0,9174** | **10,84%** |
| **HistGradientBoosting Log** | **Teste** | **US$ 64.720** | **US$ 120.736** | **0,8956** | **11,95%** |

No campeão, o R² cai 0,0217 e o RMSE do teste equivale a 1,149 vez o RMSE do treino. Existe perda fora da amostra, mas não colapso de generalização. Em relação à Regressão Linear, o RMSE de teste diminui 25,3%.

---

## 13. Diagnóstico dos erros

| Faixa do preço real | Registros | Preço mediano | MAE | MAPE | P90 do erro absoluto |
|---|---:|---:|---:|---:|---:|
| Q1 — menor preço | 1.081 | US$ 259.000 | US$ 35.573 | 15,70% | US$ 81.032 |
| Q2 | 1.086 | US$ 387.933 | US$ 40.128 | 10,40% | US$ 87.434 |
| Q3 | 1.092 | US$ 538.000 | US$ 53.022 | 9,73% | US$ 115.466 |
| Q4 — maior preço | 1.065 | US$ 845.800 | US$ 131.377 | 12,01% | US$ 294.696 |

O resíduo médio é +US$ 2.729 e a mediana é −US$ 1.930, pequenos diante da escala do alvo. A dispersão cresce no quartil superior, justificando uma regra operacional de revisão humana para imóveis de alto padrão.

---

## 14. Gráficos e evidências

### Painel geoespacial do valor residencial

A malha H3 foi calibrada com os próprios dados. Na resolução 7, o corte mínimo de 20 vendas conserva **20.014 transações (92,6%)** e produz 290 células comparáveis; na resolução 8, o mesmo corte preservaria somente 40,2% das vendas. Por isso, a resolução 7 oferece o melhor equilíbrio entre detalhe territorial e estabilidade amostral.

O decil superior começa em aproximadamente **US$ 3.824/m²**. As três células de maior mediana têm ZIP predominante 98004, entre **US$ 5.657 e US$ 5.896/m²**. O resultado descreve a concentração das vendas de 2014–2015: não representa causalidade, avaliação individual ou informação disponível para alimentar o modelo.

<p align="center">
  <a href="https://htmlpreview.github.io/?https://github.com/rica-ia/Modelo-Preditivo-Imobiliario/blob/main/outputs/maps/painel_geoespacial.html">
    <img src="https://img.shields.io/badge/Abrir-Painel%20geoespacial-21485f?style=for-the-badge&logo=leaflet&logoColor=white" alt="Abrir painel geoespacial">
  </a>
  <a href="outputs/maps/painel_geoespacial.html?raw=1">
    <img src="https://img.shields.io/badge/Baixar-Arquivo%20HTML-b08d57?style=for-the-badge&logo=html5&logoColor=white" alt="Baixar painel em HTML">
  </a><br>
  <sub>Camadas H3, transações e sobreposição; filtros, mapas-base, ranking, exportação e ajuste automático à área com vendas visíveis.</sub>
</p>

O painel é o artefato cartográfico da entrega. Ele substitui a geração redundante de PNG e SVG: a exploração permanece navegável, enquanto [`regioes_h3_valor_m2.csv`](outputs/maps/regioes_h3_valor_m2.csv) e [`resumo_mapa_valor_m2.json`](outputs/maps/resumo_mapa_valor_m2.json) preservam os números usados na interpretação. Como o repositório é privado, a prévia por serviço externo pode não receber autorização do GitHub; nesse caso, basta baixar o HTML pelo segundo botão e abri-lo no navegador.

| Posição | ZIP predominante | Mediana | Vendas | Preço mediano |
|---:|---:|---:|---:|---:|
| 1 | 98004 | US$ 5.896/m² | 41 | US$ 1.629.000 |
| 2 | 98004 | US$ 5.843/m² | 95 | US$ 1.650.000 |
| 3 | 98004 | US$ 5.657/m² | 53 | US$ 888.000 |
| 4 | 98112 | US$ 5.424/m² | 52 | US$ 1.520.000 |
| 5 | 98119 | US$ 5.344/m² | 38 | US$ 1.235.000 |

### Evidências visuais centrais

| Arquivo | Conteúdo |
|---|---|
| [`01_distribuicao_preco.png`](outputs/figures/01_distribuicao_preco.png?raw=1) | preço original e após `log1p` |
| [`02_relacoes_preco.png`](outputs/figures/02_relacoes_preco.png?raw=1) | área construída e padrão construtivo versus preço |
| [`03_correlacao_pearson.png`](outputs/figures/03_correlacao_pearson.png?raw=1) | mapa de correlação numérica |
| [`04_boxplots_outliers.png`](outputs/figures/04_boxplots_outliers.png?raw=1) | diagnóstico de extremos |
| [`05_validacao_cruzada_modelos.png`](outputs/figures/05_validacao_cruzada_modelos.png?raw=1) | estabilidade dos candidatos por fold e comparação com a média do treino |
| [`06_generalizacao_modelos.png`](outputs/figures/06_generalizacao_modelos.png?raw=1) | RMSE e R² de treino versus teste |
| [`07_real_vs_previsto.png`](outputs/figures/07_real_vs_previsto.png?raw=1) | preços reais e previstos no holdout |
| [`08_residuos.png`](outputs/figures/08_residuos.png?raw=1) | distribuição e padrão dos resíduos |
| [`09_importancia_permutacao.png`](outputs/figures/09_importancia_permutacao.png?raw=1) | dependência preditiva no teste |
| [`maps/painel_geoespacial.html`](outputs/maps/painel_geoespacial.html?raw=1) | H3, vendas, sobreposição, filtros, ranking, zoom e ajuste às vendas |
| [`maps/regioes_h3_valor_m2.csv`](outputs/maps/regioes_h3_valor_m2.csv?raw=1) | mediana, IQR, preço, área, cobertura e indicador de decil superior |

<table class="visual-grid" width="100%">
  <tr>
    <td width="50%" valign="top" align="center"><img src="outputs/figures/01_distribuicao_preco.png" alt="Distribuição do preço" width="100%"><br><b>Distribuição do alvo</b><br><sub>A transformação logarítmica reduz a assimetria de 4,024 para 0,428.</sub></td>
    <td width="50%" valign="top" align="center"><img src="outputs/figures/05_validacao_cruzada_modelos.png" alt="Validação cruzada" width="100%"><br><b>Seleção no treino</b><br><sub>O modelo logarítmico vence os cinco folds agrupados.</sub></td>
  </tr>
  <tr>
    <td width="50%" valign="top" align="center"><img src="outputs/figures/06_generalizacao_modelos.png" alt="Generalização dos modelos" width="100%"><br><b>Treino × teste</b><br><sub>O gap existe, mas não caracteriza colapso fora da amostra.</sub></td>
    <td width="50%" valign="top" align="center"><img src="outputs/figures/07_real_vs_previsto.png" alt="Real versus previsto" width="100%"><br><b>Teste isolado</b><br><sub>O alinhamento é mais forte na faixa central do mercado.</sub></td>
  </tr>
  <tr>
    <td width="50%" valign="top" align="center"><img src="outputs/figures/08_residuos.png" alt="Diagnóstico de resíduos" width="100%"><br><b>Resíduos</b><br><sub>A dispersão aumenta no segmento de maior valor.</sub></td>
    <td width="50%" valign="top" align="center"><img src="outputs/figures/09_importancia_permutacao.png" alt="Importância por permutação" width="100%"><br><b>Dependência preditiva</b><br><sub>Localização, área e padrão concentram o sinal preditivo.</sub></td>
  </tr>
</table>

<details>
  <summary><strong>Ver diagnósticos exploratórios complementares</strong></summary>
  <br>
  <table class="visual-grid" width="100%">
    <tr>
      <td width="50%" valign="top" align="center"><img src="outputs/figures/02_relacoes_preco.png" alt="Relações entre atributos e preço" width="100%"><br><b>Relações com o alvo</b></td>
      <td width="50%" valign="top" align="center"><img src="outputs/figures/03_correlacao_pearson.png" alt="Correlação de Pearson" width="100%"><br><b>Correlação numérica</b></td>
    </tr>
    <tr>
      <td colspan="2" align="center"><img src="outputs/figures/04_boxplots_outliers.png" alt="Diagnóstico de extremos" width="100%"><br><b>Extremos e consistência</b></td>
    </tr>
  </table>
</details>

### Variáveis de maior importância no teste

O valor abaixo representa quanto o MAE aumenta, em média, quando a variável é embaralhada. A medida é preditiva e não deve ser interpretada como efeito causal.

| Variável | Aumento médio do MAE |
|---|---:|
| `lat` | US$ 108.611 |
| `sqft_living` | US$ 68.161 |
| `grade` | US$ 45.221 |
| `long` | US$ 24.396 |
| `zipcode` | US$ 9.192 |
| `sqft_lot` | US$ 9.141 |
| `yr_built` | US$ 7.356 |
| `sqft_living15` | US$ 7.277 |

### Tabelas e relatórios reproduzíveis

| Artefato | Evidência preservada |
|---|---|
| [`correlacoes_pearson_spearman.csv`](outputs/correlacoes_pearson_spearman.csv) | associações lineares e monotônicas com o alvo |
| [`diagnostico_distribuicao_alvo.csv`](outputs/diagnostico_distribuicao_alvo.csv) | redução mensurada da assimetria e da curtose após `log1p` |
| [`vif_antes.csv`](outputs/vif_antes.csv) e [`vif_depois.csv`](outputs/vif_depois.csv) | redução documentada da multicolinearidade |
| [`cv_modelos_folds.csv`](outputs/cv_modelos_folds.csv) | resultado de cada candidato em cada fold agrupado |
| [`cv_modelos_resumo.csv`](outputs/cv_modelos_resumo.csv) | médias e desvios usados na seleção do campeão |
| [`vitorias_por_fold.csv`](outputs/vitorias_por_fold.csv) | vencedor por RMSE em cada uma das cinco divisões |
| [`metricas_modelos.csv`](outputs/metricas_modelos.csv) | métricas de treino e teste dos quatro modelos |
| [`diagnostico_generalizacao.csv`](outputs/diagnostico_generalizacao.csv) | gaps de erro e R² fora da amostra |
| [`erros_por_faixa_preco.csv`](outputs/erros_por_faixa_preco.csv) | erro segmentado pelos quartis do preço real |
| [`resumo_residuos.json`](outputs/resumo_residuos.json) | centro, dispersão e proporções de erro absoluto |
| [`importancia_permutacao.csv`](outputs/importancia_permutacao.csv) | importância e desvio das 19 variáveis explicativas |
| [`relatorio_qualidade_dados.json`](outputs/relatorio_qualidade_dados.json) | auditoria e tratamentos de qualidade aplicados |
| [`regioes_h3_valor_m2.csv`](outputs/maps/regioes_h3_valor_m2.csv) | 290 células, amostra, preço, área, IQR e decil superior |
| [`resumo_mapa_valor_m2.json`](outputs/maps/resumo_mapa_valor_m2.json) | resolução, cobertura, escala e limiar espacial |

---

## 15. Veredito de negócio

| Aplicação | Veredito |
|---|---|
| Triagem e priorização do portfólio | adequado |
| Faixa inicial de anúncio | adequado como apoio |
| Identificação de preços muito discrepantes | adequado |
| Fechamento do preço final | inadequado sem avaliação humana |
| Financiamento ou garantia | inadequado como única evidência |
| Imóveis de alto padrão | encaminhar para avaliação especializada |

---

## 16. Versionamento do modelo — v1

A pasta `models/v1/` contém:

- [`modelo_regressao_v1.pkl`](models/v1/modelo_regressao_v1.pkl?raw=1): engenharia de atributos sobre o esquema bruto, `ColumnTransformer`, transformação logarítmica do alvo, correção de retransformação e HistGradientBoosting retreinados nas 21.613 vendas;
- [`metricas_v1.json`](models/v1/metricas_v1.json?raw=1): data UTC do treinamento, configuração, validação cruzada, métricas do holdout e 19 variáveis explicativas.

As métricas registradas permanecem as do teste isolado; elas não são recalculadas sobre a base completa. Uma alteração de dados, features ou algoritmo deve gerar uma nova pasta (`v2`, `v3`), preservando a comparação.

### Estratégia de branches

| Branch | Responsabilidade | Regra de integração |
|---|---|---|
| `main` | versão estável destinada à entrega | recebe a solução somente após benchmark e auditoria final |
| `develop` | integração das fases acadêmicas e da documentação | recebe checkpoints reais e o experimento aprovado |
| `experiment/modelos` | comparação entre a média do treino, Regressão Linear, HistGradientBoosting e variante logarítmica | merge `--no-ff` na `develop` somente após o resultado de validação cruzada |

O experimento é funcional: caso um candidato não supere o baseline de forma consistente, sua branch não precisa ser integrada. Neste projeto, a variante logarítmica venceu os cinco folds e justificou o merge, preservando a `main` até a conclusão das demais verificações.

---

## 17. Como executar

### Ambiente único

O projeto é desenvolvido, executado e versionado exclusivamente no **Google Colab**. Não é necessário configurar Python, Jupyter ou ambiente virtual local.

Para reproduzir a versão pública:

1. abra o notebook pelo botão **Abrir no Google Colab**;
2. escolha **Ambiente de execução → Executar tudo**;
3. aguarde a primeira célula de código instalar somente dependências ausentes, baixar a base pública do Google Drive e validar seu SHA-256;
4. confira a execução sequencial das seis fases e os artefatos regenerados em `outputs/` e `models/v1/`.

A cópia acadêmica é autônoma: não exige upload manual, montagem do Drive, autenticação no Google ou token do GitHub; basta conexão à internet e acesso público de leitura ao repositório e ao dataset. No fluxo privado, o mesmo notebook contém temporariamente os comandos Git: as fases iniciais são registradas na `develop`, a comparação de modelos ocorre em `experiment/modelos`, o benchmark integral roda em um runtime novo e a `main` só é consolidada depois da sanitização e da auditoria.

### Política das células

| Tipo | Permanece na entrega? | Conteúdo |
|---|---|---|
| Acadêmica | sim | 15 células de código: numeração principal 0–10, com células de apoio visual e geoespacial na Fase 1 |
| Operacional temporária | não | sessão, autenticação, checkpoint, criação de branch, merges, benchmark e auditoria durante a construção |

O repositório público rastreia apenas um `.ipynb`. As células operacionais são removidas da versão indexada em cada checkpoint e da cópia final; credenciais nunca aparecem no notebook, no remote, nas saídas ou no histórico.

### Carregamento e previsão

```python
import joblib
import pandas as pd

modelo = joblib.load("models/v1/modelo_regressao_v1.pkl")
novos = pd.read_csv("novos_imoveis.csv")
previsoes = modelo.predict(novos)
```

`novos_imoveis.csv` deve seguir o esquema bruto das 19 entradas listadas em `metricas_v1.json`. `id` e `price` não são exigidos: correção contextual, engenharia de atributos, imputação, escala, encoding e previsão são executados pelo próprio pipeline.

---

## 18. Dependências e reprodutibilidade

| Biblioteca | Versão | Finalidade |
|---|---:|---|
| Python | 3.12.x | linguagem e execução; versão efetiva registrada ao final |
| Pandas | 2.2.3 | carga, limpeza e exportação |
| NumPy | 2.3.5 | operações numéricas e resíduos |
| scikit-learn | 1.8.0 | divisão, preprocessamento, modelos, métricas e validação |
| Matplotlib | 3.10.8 | gráficos |
| Seaborn | 0.13.2 | visualizações estatísticas |
| SciPy | 1.17.0 | suporte científico |
| Joblib | 1.5.3 | serialização do modelo |
| H3 | 4.5.0 | indexação geoespacial hexagonal |
| Plotly | 6.8.0 | prévia H3 incorporada ao notebook |
| Jinja2 | 3.1.6 | formatação das tabelas analíticas no notebook |
| Leaflet | 1.9.4 | painel cartográfico standalone carregado no navegador |

Controles de reprodução:

- Google Colab como único ambiente de desenvolvimento e execução;
- funções acadêmicas incorporadas ao notebook e dataset público carregado do Google Drive, sem upload manual; o CSV só é aceito após conferência SHA-256;
- verificação prévia das bibliotecas, com instalação somente das dependências ausentes ou abaixo da versão mínima;
- base bruta preservada em `data/raw/`;
- `random_state=42` nas divisões e nos modelos;
- holdout e folds agrupados por `id`;
- transformações ajustadas somente no treino de cada divisão;
- dependências fixadas em `requirements.txt`;
- ambiente efetivo registrado em `environment_info.json`;
- painel espacial reproduzido a partir de coordenadas e limite oficial do condado, sem token cartográfico;
- notebook entregue com seis fases avaliativas explícitas, conclusão e nenhuma célula operacional;
- checkpoints graduais realizados na `develop` e em `experiment/modelos`, imediatamente após cada fase e com timestamp real;
- experimento integrado à `develop` por merge `--no-ff` somente após a comparação dos candidatos;
- execução integral cronometrada em runtime novo do Colab antes da consolidação;
- duração, versão do Python e status gravados em `outputs/tempo_execucao_colab.json` nessa validação;
- integração da `develop` na `main` por merge commit, somente após a sanitização e a auditoria final.

---

## 19. Limitações

| Limitação | Impacto |
|---|---|
| Vendas de 2014–2015 | não incorpora inflação nem mudanças recentes do mercado |
| Base restrita a King County | não sustenta generalização automática para outras regiões |
| Atributos externos ausentes | escolas, transporte, ruído e micro-localização podem explicar erro restante |
| Erro heterogêneo | imóveis caros têm erro absoluto maior |
| Previsão pontual | não oferece intervalo individual de incerteza |
| Validação aleatória agrupada | não substitui uma validação temporal para implantação futura |
| Importância por permutação | mede dependência preditiva, não causalidade |

---

## 20. Roadmap de evolução: venda, aluguel e short stay

A base de 2014–2015 permanece útil como **benchmark histórico e acadêmico**, não como fotografia do mercado atual. A próxima versão deve começar pela ingestão contínua de dados recentes e reservar o período mais novo como teste fora do tempo. Assim, o projeto deixa de apenas estimar o preço de venda e evolui para uma plataforma de decisão imobiliária com três produtos conectados.

### 20.1 Produtos preditivos e financeiros

| Produto | Alvos modelados | Saída útil para decisão |
|---|---|---|
| Valor de venda | preço de transação e preço por m² ajustado por tipologia e localização | valor justo, intervalo de incerteza e comparação com imóveis semelhantes |
| Aluguel tradicional | aluguel mensal, probabilidade de vacância e tempo esperado até locação | receita anual ajustada à vacância, yield bruto e renda líquida estimada |
| Airbnb / short stay | diária média (`ADR`) e taxa de ocupação, modeladas separadamente por data e microrregião | receita por cenário, sazonalidade, noites vendidas e risco de baixa ocupação |
| Investimento | fluxo de caixa depois de despesas, financiamento e impostos | `NOI`, cap rate, cash-on-cash, `DSCR`, valor presente líquido, TIR e prazo de retorno |

Para short stay, a projeção bruta deve ser calculada como `ADR × noites disponíveis × ocupação`. O fluxo líquido precisa descontar taxa da plataforma, gestão, limpeza não repassada, utilidades, condomínio, seguro, impostos, manutenção, reposição de mobiliário, vacância e restrições locais. A apresentação correta é por cenários conservador, base e otimista; não como promessa de “renda passiva”.

### 20.2 Dados atuais e arquitetura espacial

1. **Atualização ponto no tempo:** formar snapshots mensais ou semanais de anúncios, transações, disponibilidade e atributos vigentes na data da previsão. Isso impede que uma informação posterior à venda ou à reserva vaze para o treino.
2. **Fontes complementares:** combinar registros cadastrais e de transações com [HUD FMR/SAFMR](https://www.huduser.gov/portal/datasets/fmr.html), [Zillow ZORI](https://www.zillow.com/research/data/) e dados públicos ou licenciados de short stay, como os conjuntos documentados pelo [Inside Airbnb](https://insideairbnb.com/get-the-data/). Coleta automatizada só deve ocorrer quando licença e termos de uso permitirem.
3. **Contexto urbano e de risco:** acrescentar tempo de viagem a polos de emprego, transporte, escolas, amenidades, zoneamento, licenças de hospedagem, ruído, criminalidade agregada, enchente, incêndio, clima, eventos, feriados, juros e indicadores de renda e emprego.
4. **Camadas geoespaciais:** armazenar parcelas, pontos de interesse, isócronas e células H3 em PostgreSQL com [PostGIS](https://postgis.net/docs/); usar índices espaciais, vizinhança e distâncias calculadas no banco, preservando a geografia válida em cada data.
5. **Processamento reproduzível:** manter zonas `raw`, `validated` e `features`; usar SQL/[dbt](https://docs.getdbt.com/docs/introduction) para transformações auditáveis, [DuckDB Spatial](https://duckdb.org/docs/stable/core_extensions/spatial/overview) e [Polars](https://docs.pola.rs/) para análise local eficiente, e [DVC](https://dvc.org/doc) para versionar referências dos dados sem inflar o Git.
6. **Atributos multimodais:** quando houver autorização e histórico suficiente, extrair sinais de descrições, fotografias e plantas para representar conservação, luminosidade, vista e padrão de acabamento. Esses atributos devem respeitar licença, privacidade e data de disponibilidade, e só permanecem se melhorarem o backtest fora do tempo.

### 20.3 Validação e modelagem de segunda geração

- Substituir a validação aleatória como evidência de implantação por **backtesting com origem móvel**: vários cortes cronológicos, imóvel agrupado por `id` e último período totalmente intocado. Acrescentar blocos espaciais para medir desempenho em regiões não vistas ou pouco representadas.
- Preservar um baseline hedônico interpretável e comparar [CatBoost](https://catboost.ai/docs/en/), [LightGBM](https://lightgbm.readthedocs.io/en/stable/) e [XGBoost](https://xgboost.readthedocs.io/en/stable/). O ajuste com [Optuna](https://optuna.readthedocs.io/en/stable/) deve ocorrer apenas dentro do treino; complexidade só é aceita quando melhora o teste temporal e espacial.
- Estimar quantis e aplicar predição conformal com [MAPIE](https://mapie.readthedocs.io/en/latest/) para fornecer intervalos de 80% e 90%. Além de MAE e RMSE, acompanhar cobertura, largura média do intervalo e cobertura por ZIP, faixa de preço e tipo de imóvel.
- Para aluguel tradicional, modelar simultaneamente valor mensal e vacância. Para short stay, adotar arquitetura em duas etapas — ocupação e `ADR` — com variáveis de calendário, eventos, defasagens e oferta concorrente; modelos profundos de séries temporais só entram se houver histórico longitudinal suficiente para superar os métodos tabulares.
- Investigar o erro espacial remanescente com econometria e modelos hierárquicos em **R** (`sf`, `spdep`, `brms`) ou Python (`PyMC`). Essa trilha serve para quantificar efeitos por bairro e dependência espacial, não para substituir automaticamente o melhor preditor validado.
- Separar previsão de causalidade: estimar o valor de um imóvel é uma tarefa; medir retorno de reforma, piscina ou mudança regulatória exige desenho causal próprio, com grupos comparáveis e hipóteses declaradas.

### 20.4 Stack profissional sugerido

| Camada | Tecnologias | Papel no sistema |
|---|---|---|
| Dados e geografia | SQL, PostgreSQL/PostGIS, dbt, DuckDB Spatial, Polars | ingestão incremental, contratos, consultas espaciais e criação de atributos |
| Ciência de dados | Python/scikit-learn, CatBoost, LightGBM, XGBoost, MAPIE; R para auditoria espacial e bayesiana | modelos pontuais, intervalos, sazonalidade e diagnóstico |
| Qualidade e versionamento | [Pandera](https://pandera.readthedocs.io/en/stable/), testes dbt, DVC e GitHub Actions | validar esquema, impedir regressões e ligar código à versão dos dados |
| Experimentos e modelos | [MLflow Tracking e Model Registry](https://mlflow.org/docs/latest/ml/model-registry/) | rastrear parâmetros, métricas, linhagem, versões e aliases `champion`/`challenger` |
| Orquestração | [Prefect](https://docs.prefect.io/v3/get-started) | agendar ingestão, treinamento, avaliação e publicação com retries observáveis |
| Serviço | [FastAPI](https://fastapi.tiangolo.com/), [Docker](https://docs.docker.com/) e armazenamento de objetos | disponibilizar previsões versionadas com contrato de entrada e rollback |
| Experiência geoespacial | TypeScript, React e MapLibre GL JS | simulador responsivo com mapa, cenários, comparáveis e intervalos |
| Monitoramento | [Evidently](https://docs.evidentlyai.com/docs/platform/monitoring_overview), testes de distribuição e alertas de negócio | detectar drift de dados, degradação de erro, queda de cobertura e descalibração |

Uma feature store como Feast e processamento distribuído com Spark só se justificam quando houver múltiplos consumidores, baixa latência ou volume que ultrapasse a arquitetura SQL/DuckDB. Antecipar essa complexidade no volume atual aumentaria custo sem evidência de ganho.

### 20.5 Sequência recomendada e critérios de promoção

| Prioridade | Entrega | Critério para avançar |
|:---:|---|---|
| P0 | dados atuais, contratos de esquema, snapshots ponto no tempo e catálogo de fontes/licenças | atualização reproduzível, sem vazamento e com cobertura temporal e espacial medida |
| P1 | modelo de venda v2 com boosting, validação temporal-espacial e intervalos conformais | reduzir erro fora do tempo e atingir cobertura nominal por segmento sem intervalos impraticáveis |
| P2 | modelos de aluguel mensal, ocupação e `ADR`; motor de custos e cenários | erro estável por estação e região, cálculos financeiros reconciliáveis e premissas editáveis |
| P3 | API, painel de investimento e camada cartográfica em TypeScript/MapLibre | resposta versionada, rastreável e consistente entre API, mapa e relatório financeiro |
| P4 | pipeline automatizado, registro de modelos e monitoramento `champion/challenger` | promover somente quando o candidato superar o campeão em métricas técnicas e de negócio |

O resultado esperado não é apenas um algoritmo com R² maior. É um sistema que informa **quanto um imóvel pode valer, quanto pode render, qual a incerteza da estimativa e quais premissas alteram o retorno**, com rastreabilidade suficiente para explicar cada cenário.

---

## 21. Transparência sobre uso de IA

Ferramentas de inteligência artificial foram utilizadas como apoio auxiliar na organização, revisão e aprimoramento da apresentação do projeto, mantendo a responsabilidade técnica e autoral do aluno. As decisões de tratamento, modelagem, validação e interpretação foram conferidas pelo autor a partir dos dados e das evidências reproduzíveis disponibilizadas neste repositório.

---

## 22. Fonte, licença e autor

Dataset fornecido no enunciado do projeto: `kc_house_data.csv`.

Licença MIT — consulte [`LICENSE`](LICENSE).

**Ricardo Pasquali dos Reis**
Desenvolvimento em IA para Análise Preditiva
