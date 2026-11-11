# Toqan chat demo

O agente roda aqui, e cada chamada de modelo passa pelo Toqan Router. Há duas personas, e você escolhe uma no topo da tela:

- **Comprador**: um agente de compras com mandato. O cliente diz o que quer, e o agente busca no catálogo, monta o carrinho, compara Pix com parcelado e paga. Ele não passa de R$ 300 por pedido; esse limite está no código da tool, não no prompt.
- **Lojista**: o copiloto do caixa de uma cafeteria. Mostra vendas, explica recusas e chargebacks, mostra a agenda de recebíveis e gera links de pagamento.

Cada cenário marca a chamada com identidade e metadados, e assim uma regra do workspace `toqan` entra em ação. Cada resposta tem um link para o trace no Toqan.

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
- No workspace `toqan`, o cache dá `cache-miss` em todas as chamadas, tanto pela regra quanto pelo parâmetro `cache`. No `toqan-workshop` funciona.
- `orq:web_search` e `orq:web_fetch` respondem `no responders available`, por isso ficaram de fora. Smart router com server tool dá 403.
- O firewall de input olha a mensagem do usuário, não o resultado das tools. Contra a injeção indireta, a defesa é o prompt e o mandato no código.

## Vercel

No ar em **https://toqan-chat.vercel.app** (projeto `toqan-chat`, time `arianpasquali-4998s-projects`), com Vercel Authentication em todas as URLs, inclusive a de produção: só abre logado no time. `TOQAN_API_KEY` está guardada como variável sensível em Production e Preview. O push não faz deploy; o deploy é manual, de dentro da pasta: `cd toqan-chat && vercel deploy --prod`.


O app não guarda estado (o navegador reenvia `history`), então roda no Vercel sem mudanças. Não desligue a proteção: sem ela, a URL vira um proxy público para a chave do Toqan.
