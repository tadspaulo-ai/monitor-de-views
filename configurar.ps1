# Configurador do Monitor de Views
# Guarda as chaves como segredos criptografados do GitHub e autoriza a conta do TikTok.
# Nada do que voce digitar aqui aparece na tela nem fica salvo no PC.
param([string]$Repo = 'tadspaulo-ai/monitor-de-views', [switch]$SoTikTok, [switch]$SoGmail)

$ErrorActionPreference = 'Stop'
$gh = 'C:\Program Files\GitHub CLI\gh.exe'
[Console]::OutputEncoding = [Text.Encoding]::UTF8

function Read-Segredo([string]$texto) {
  $s = Read-Host -Prompt $texto -AsSecureString
  $p = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
  try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($p).Trim() } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p) }
}
function Set-Segredo([string]$nome, [string]$valor) {
  if ([string]::IsNullOrWhiteSpace($valor)) { Write-Host "  (pulado: $nome)" -ForegroundColor DarkGray; return }
  & $gh secret set $nome --repo $Repo --body $valor | Out-Null
  Write-Host "  OK: $nome guardado no GitHub" -ForegroundColor Green
}

Write-Host ''
Write-Host '=== Monitor de Views - configuracao ===' -ForegroundColor Cyan
Write-Host 'Deixe em branco e aperte Enter para pular qualquer item.'
Write-Host ''

if (-not $SoTikTok) {
 if (-not $SoGmail) {
  Write-Host '--- YouTube ---' -ForegroundColor Yellow
  Set-Segredo 'YT_API_KEY' (Read-Segredo 'Cole a chave da API do YouTube (Google Cloud > Credenciais)')
  Set-Segredo 'YT_CHANNEL' (Read-Host 'Seu canal do YouTube (ex.: @seucanal)').Trim()
 }
  Write-Host ''
  Write-Host '--- E-mail (Gmail) ---' -ForegroundColor Yellow
  Write-Host 'Use o endereco COMPLETO (ex.: nome@gmail.com) e a senha de app, NAO a senha normal do Gmail.'
  Write-Host 'Senha de app: myaccount.google.com/apppasswords (precisa da verificacao em 2 etapas ligada).'
  while ($true) {
    $gu = (Read-Host 'Seu endereco do Gmail que vai ENVIAR os relatorios').Trim()
    if (-not $gu) { break }
    $gp = (Read-Segredo 'Cole a senha de app do Gmail (16 letras)') -replace '\s', ''
    Write-Host '  Testando o login no Gmail (envia um e-mail de teste para voce)...'
    try {
      $smtp = New-Object Net.Mail.SmtpClient('smtp.gmail.com', 587)
      $smtp.EnableSsl = $true
      $smtp.Credentials = New-Object Net.NetworkCredential($gu, $gp)
      $smtp.Send($gu, $gu, 'Monitor de Views - teste', 'Se voce recebeu isto, o Gmail do Monitor de Views esta configurado.')
      Write-Host '  OK: o Gmail aceitou! Confira o e-mail de teste.' -ForegroundColor Green
      Set-Segredo 'GMAIL_USER' $gu
      Set-Segredo 'GMAIL_APP_PASSWORD' $gp
      break
    } catch {
      Write-Host "  O Gmail RECUSOU: $($_.Exception.InnerException.Message) $($_.Exception.Message)" -ForegroundColor Red
      Write-Host '  Use o endereco completo e uma SENHA DE APP (myaccount.google.com/apppasswords). Tente de novo ou Enter para pular.' -ForegroundColor Red
    }
  }
  Set-Segredo 'EMAIL_TO' (Read-Host 'E-mail que vai RECEBER os relatorios (Enter = o mesmo)').Trim()
 if (-not $SoGmail) {
  Write-Host ''
  Write-Host '--- WhatsApp (opcional, CallMeBot) ---' -ForegroundColor Yellow
  Write-Host 'Para ativar: adicione +34 644 71 81 99 nos contatos e mande "I allow callmebot to send me messages".'
  Set-Segredo 'CALLMEBOT_PHONE' (Read-Host 'Seu WhatsApp com DDI (ex.: 5511999998888) ou Enter para pular').Trim()
  Set-Segredo 'CALLMEBOT_APIKEY' (Read-Segredo 'apikey que o CallMeBot te respondeu (ou Enter)')
 }
}

Write-Host ''
Write-Host '--- TikTok ---' -ForegroundColor Yellow
Write-Host 'Client key e Client secret: developers.tiktok.com > Monitor de Views > Sandbox > Credentials.'
$ck = if ($SoGmail) { '' } else { Read-Segredo 'Cole o Client key do TikTok' }
if ($ck) {
  $cs = Read-Segredo 'Cole o Client secret do TikTok'
  Set-Segredo 'TIKTOK_CLIENT_KEY' $ck
  Set-Segredo 'TIKTOK_CLIENT_SECRET' $cs

  $redirect = 'http://localhost:8765/callback/'
  $bytes = New-Object byte[] 48; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $verifier = ([Convert]::ToBase64String($bytes) -replace '[+/=]', '')
  $sha = [Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::ASCII.GetBytes($verifier))
  $challenge = -join ($sha | ForEach-Object { $_.ToString('x2') })
  $state = [guid]::NewGuid().ToString('N')
  $q = @{ client_key = $ck; scope = 'user.info.basic,user.info.stats,video.list'; response_type = 'code';
          redirect_uri = $redirect.TrimEnd('/'); state = $state; code_challenge = $challenge; code_challenge_method = 'S256' }
  $url = 'https://www.tiktok.com/v2/auth/authorize/?' + (($q.GetEnumerator() | ForEach-Object { $_.Key + '=' + [uri]::EscapeDataString($_.Value) }) -join '&')

  $listener = New-Object Net.HttpListener
  $listener.Prefixes.Add($redirect); $listener.Start()
  Write-Host ''
  Write-Host 'Abrindo o TikTok no navegador. Entre na SUA conta do TikTok e clique em Autorizar...' -ForegroundColor Cyan
  Start-Process $url
  $ctx = $listener.GetContext()
  $code = $ctx.Request.QueryString['code']; $estado = $ctx.Request.QueryString['state']
  $html = '<html><body style="font-family:sans-serif;padding:40px"><h2>Pronto! Pode fechar esta aba e voltar para a janela do configurador.</h2></body></html>'
  $buf = [Text.Encoding]::UTF8.GetBytes($html); $ctx.Response.ContentType = 'text/html; charset=utf-8'
  $ctx.Response.OutputStream.Write($buf, 0, $buf.Length); $ctx.Response.Close(); $listener.Stop()

  if (-not $code -or $estado -ne $state) { throw 'O TikTok nao devolveu a autorizacao. Rode de novo.' }
  $tok = Invoke-RestMethod -Method Post -Uri 'https://open.tiktokapis.com/v2/oauth/token/' -ContentType 'application/x-www-form-urlencoded' -Body @{
    client_key = $ck; client_secret = $cs; code = $code; grant_type = 'authorization_code';
    redirect_uri = $redirect.TrimEnd('/'); code_verifier = $verifier }
  if (-not $tok.refresh_token) { throw "TikTok recusou: $($tok.error_description)" }
  Set-Segredo 'TIKTOK_REFRESH_TOKEN' $tok.refresh_token
  Write-Host "  Escopos autorizados: $($tok.scope)" -ForegroundColor Green
}

Write-Host ''
Write-Host 'Disparando a primeira rodada do monitor...' -ForegroundColor Cyan
& $gh workflow run monitor.yml --repo $Repo
Write-Host ''
Write-Host 'Tudo pronto! O primeiro e-mail chega em 1 a 2 minutos. Pode fechar esta janela.' -ForegroundColor Green
Read-Host 'Aperte Enter para fechar'
