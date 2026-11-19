# Monitor de Views

Ferramenta pessoal que, de hora em hora, lê as views dos meus vídeos no YouTube e no TikTok e manda um relatório por e-mail (e alertas opcionais no WhatsApp).

- `monitor.py`: coleta os números e envia o relatório.
- `.github/workflows/monitor.yml`: roda o monitor toda hora no GitHub Actions.
- `configurar.ps1`: guarda as chaves como segredos do GitHub e autoriza a conta do TikTok.
- `docs/`: site com termos de uso e política de privacidade (GitHub Pages).

## Ajustes (Settings → Secrets and variables → Actions → Variables)

| Variável | Padrão | O que faz |
|---|---|---|
| `VIRAL_POR_HORA` | 1000 | Views ganhas em 1 hora para virar alerta |
| `VIRAL_TOTAL` | 100000 | Total de views para entrar na lista de virais |
| `MODO_RELATORIO` | sempre | `alertas` = só manda e-mail quando algo estiver viralizando |
