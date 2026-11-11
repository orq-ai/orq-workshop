# Toqan chat demo

O agente roda aqui, e cada chamada de modelo passa pelo Toqan Router. Há duas personas, e você escolhe uma no topo da tela:

- **Comprador**: um agente de compras com mandato. O cliente diz o que quer, e o agente busca no catálogo, monta o carrinho, compara Pix com parcelado e paga. Ele não passa de R$ 300 por pedido; esse limite está no código da tool, não no prompt.
- **Lojista**: o copiloto do caixa de uma cafeteria. Mostra vendas, explica recusas e chargebacks, mostra a agenda de recebíveis e gera links de pagamento.

Cada cenário marca a chamada com identidade e metadados, e assim uma regra do workspace `toqan` entra em ação. Cada resposta tem um link para o trace no Toqan.

A comunicação usa a **Responses API** (`/v3/router/responses`), sem estado (`store: false`): todo item de saída volta na rodada seguinte, inclusive `reasoning` e os resultados `orq:*` das server tools.

## Achar os traces da demo no Toqan

Toda chamada leva o nome de trace `toqan-router-demo`, o metadado `app=toqan-router-demo` (além de `persona` e `cenario`) e, por conversa, uma thread `toqan-router-demo-<id>`. Para filtrar, busque `toqan-router-demo` em Traces, ou abra direto
`https://router.toqan.ai/br/toqan/traces?traces_q=toqan-router-demo&traces_range=86400000`. O mesmo link está no painel de execução e no ⚙.

## Chave da demo

O Vercel usa uma chave de serviço própria, `toqan-router-demo` (prefixo `sk-orq-940-cda1`), que também serve para demonstrar:
- **Escopo:** só o Default Project.
- **Acesso:** apenas `chat_completions`, `responses` (escrita) e `model` (leitura).
- **Validade:** vence em 11/11/2026, às 23:59 de Brasília.
- **Budget:** US$ 10 por dia e 30 requisições por minuto, com alerta por e-mail em 80% (notifier Financeiro), vencendo junto com a chave.

O router devolve o budget nos headers `x-ratelimit-*-cost`, e a demo mostra o gasto ao vivo. Localmente, a chave fica em `~/.orq/toqan-key-router-demo`.

```bash
cp toqan-chat/.env.example toqan-chat/.env   # TOQAN_API_KEY = chave do projeto do workspace toqan
make toqan-chat-ui                            # http://127.0.0.1:8003
make toqan-chat-test                          # testes sem rede
```

## Na tela

O topo tem só a persona, **↺** (nova conversa) e **⚙**. Acima do campo de mensagem ficam os cenários e as mensagens de exemplo, que funcionam com um clique. O **⚙** guarda o modelo, stream ou resposta completa, o modo **Detalhado** (modelo pedido e o que respondeu, tempos, tokens e argumentos), o painel de execução e os dados de teste. Para um link já configurado, use `?modo=detalhado` ou `?modo=simples`.

## Cenários

| Cenário | O que vai na chamada | No Toqan |
|---|---|---|
| Livre | identity `produto` | só o trace |
| Roteamento 80/20 | usecase `atendimento` | regra por peso: GPT-OSS 80%, DeepSeek 20% |
| Cache | usecase `perguntas-frequentes` | regra de cache de 1 h (uma chamada, sem tools e sem histórico) |
| Firewall de IA | usecase `chat-com-cliente` | guardrail: cartão, CPF, injeção, promessa fora da política. Sempre resposta completa |
| VIP · sempre Opus | identity `diretoria` | regra por identidade → Claude Opus |
| Fallback | modelo Haiku 4.5 Bedrock (404) | regra de fallback → GPT-OSS |
| Ferramentas do router | `orq:code_interpreter`, `orq:advisor` (Opus), `orq:datetime` | o router roda as ferramentas sozinho |

Para mostrar defesa em camadas na persona Comprador:
1. Peça o "Kit presente premium" no cenário Livre. A descrição do produto traz uma ordem escondida, e o agente a ignora.
2. "Eu autorizo passar do limite…": se o modelo tentar pagar, a tool recusa (`acima_do_mandato`).
3. No Firewall, o cartão colado no chat é bloqueado antes de chegar ao modelo.

## Limitações conhecidas (11 nov 2026, BR)

- O router é chamado sempre em stream, menos no firewall. Sem stream, os modelos abertos no Bedrock (DeepSeek, GPT-OSS, Kimi) devolvem os argumentos das tools vazios (`"{}"`).
- O cache do workspace `toqan` voltou a funcionar em 11/11, depois de um ajuste de configuração. Um hit vem com 0 tokens e custo zero, e a demo mostra "do cache". A thread entra na chave do cache, por isso o FAQ é enviado sem thread.
- Na Responses API, os smart routers com tools levam de 10 a 11 s por chamada, contra uns 3 s no chat/completions.
- `orq:web_search` e `orq:web_fetch` respondem `no responders available`, por isso ficaram de fora. Smart router com server tool dá 403.
- O firewall de input olha a mensagem do usuário, não o resultado das tools. Contra a injeção indireta, a defesa é o prompt e o mandato no código.

## Vercel

No ar, **aberto**, em **https://toqan-router-demo.vercel.app** (projeto `toqan-router-demo`, time `arianpasquali-4998s-projects`). O que segura o custo: a chave da demo (budget e expiração), a lista fechada de modelos e o limite de tamanho das mensagens no app. `TOQAN_API_KEY` está guardada como variável sensível em Production e Preview. O push não faz deploy; o deploy é manual, de dentro da pasta: `cd toqan-chat && vercel deploy --prod`.


O app não guarda estado (o navegador reenvia `history`), então roda no Vercel sem mudanças. Depois de hoje a chave vence e a demo para de responder. Para reabrir, crie outra chave e troque `TOQAN_API_KEY`, ou religue a proteção (`ssoProtection: {"deploymentType": "all"}`).
