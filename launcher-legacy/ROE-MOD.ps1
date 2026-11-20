param([switch]$Check, [string]$GameDirectory)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
. (Join-Path $PSScriptRoot 'Accounts.ps1')

$settingsFile = Join-Path $PSScriptRoot 'profiles.json'
$registryPath = 'Software\Cyber Warrior\LithtechRubies'
$profiles = @{
    Local = [pscustomobject]@{ Endpoint = '127.0.0.1'; Server = ''; Arguments = ''; ReadyPort = ''; Cloudflared = ''; Tunnel = '' }
    Public = [pscustomobject]@{ Endpoint = ''; Server = ''; Arguments = ''; ReadyPort = ''; Cloudflared = ''; Tunnel = '' }
}

function Find-GameClient {
    $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey('LocalMachine', 'Registry32')
    try {
        $key = $base.OpenSubKey($registryPath)
        $registered = if ($key) {
            try { $key.GetValue('SourceDirectory', '') } finally { $key.Dispose() }
        }
    } finally { $base.Dispose() }
    $fallback = Join-Path ${env:ProgramFiles(x86)} 'Rubies of Eventide'
    $directories = if ($GameDirectory) { @($GameDirectory) } else { @($registered, $fallback, $PWD.Path) }
    foreach ($directory in $directories) {
        if (-not $directory) { continue }
        $candidate = Join-Path $directory 'Lithtech.exe'
        if ((Test-Path -LiteralPath $candidate -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $directory 'rez\CShell.dll') -PathType Leaf)) {
            return (Get-Item -LiteralPath $candidate).FullName
        }
    }
    throw 'Rubies of Eventide was not found. Install the client or start ROE:MOD with -GameDirectory and its install path.'
}
function Read-LoginServer {
    $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey('LocalMachine', 'Registry32')
    try {
        $key = $base.OpenSubKey($registryPath)
        if ($null -ne $key) {
            try { $key.GetValue('LoginServer', '') } finally { $key.Dispose() }
        }
    } finally { $base.Dispose() }
}

function Set-LoginServer([string]$Endpoint) {
    if ([uri]::CheckHostName($Endpoint) -notin 'Dns', 'IPv4' -or $Endpoint -notmatch '^[a-zA-Z0-9.-]{1,253}$') {
        throw 'Enter a DNS hostname or IPv4 address without a port.'
    }
    if ((Read-LoginServer) -eq $Endpoint) { return }
    # The original 32-bit client reads this machine-wide value.
    $command = @"
`$ErrorActionPreference = 'Stop'
`$base = [Microsoft.Win32.RegistryKey]::OpenBaseKey('LocalMachine', 'Registry32')
`$key = `$base.CreateSubKey('$registryPath')
try { `$key.SetValue('LoginServer', '$Endpoint', 'String') } finally { `$key.Dispose(); `$base.Dispose() }
"@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    $helper = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -Verb RunAs -WindowStyle Hidden -ArgumentList '-NoProfile', '-EncodedCommand', $encoded -Wait -PassThru
    if ($helper.ExitCode -ne 0 -or (Read-LoginServer) -ne $Endpoint) { throw 'Windows did not apply the game login address.' }
}

function Start-Component([string]$Path, [string]$Arguments) {
    $processOptions = @{
        FilePath = $Path
        WorkingDirectory = Split-Path -Parent $Path
        PassThru = $true
    }
    if ($Arguments.Trim()) { $processOptions.ArgumentList = $Arguments }
    Start-Process @processOptions
}

function Resolve-Executable([string]$Path) {
    if (-not $Path -or -not [IO.Path]::IsPathRooted($Path) -or [IO.Path]::GetExtension($Path) -ne '.exe' -or
        -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw 'Choose an existing Windows .exe file using its full path.'
    }
    (Get-Item -LiteralPath $Path).FullName
}

function Wait-ForServer($Process, [int]$Port) {
    if ($Port -eq 0) {
        if ($Process.WaitForExit(1200)) { throw "The server exited with code $($Process.ExitCode)." }
        return
    }
    $deadline = [DateTime]::UtcNow.AddSeconds(20)
    do {
        if ($Process.HasExited) { throw "The server exited with code $($Process.ExitCode)." }
        $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
            Where-Object OwningProcess -eq $Process.Id
        if ($listener) { return }
        Start-Sleep -Milliseconds 300
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "The server process did not listen on TCP port $Port within 20 seconds. Check its console and the readiness port."
}

if (Test-Path -LiteralPath $settingsFile) {
    $saved = Get-Content -LiteralPath $settingsFile -Raw | ConvertFrom-Json
    foreach ($mode in 'Local', 'Public') {
        foreach ($field in $profiles[$mode].PSObject.Properties.Name) {
            $profiles[$mode].$field = [string]$saved.$mode.$field
        }
    }
}
if ($Check) {
    [pscustomobject]@{ Client = (Find-GameClient); LoginServer = (Read-LoginServer) }
    return
}

$form = New-Object Windows.Forms.Form
$form.Text = 'ROE:MOD'
$form.ClientSize = New-Object Drawing.Size(620, 450)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.Font = New-Object Drawing.Font('Segoe UI', 10)

function Add-Label([string]$Caption, [int]$X, [int]$Y, [int]$Width = 590) {
    $label = New-Object Windows.Forms.Label
    $label.Text = $Caption
    $label.SetBounds($X, $Y, $Width, 25)
    $form.Controls.Add($label)
    $label
}
function Add-Button([string]$Caption, [int]$X, [int]$Y, [int]$Width) {
    $button = New-Object Windows.Forms.Button
    $button.Text = $Caption
    $button.SetBounds($X, $Y, $Width, 31)
    $form.Controls.Add($button)
    $button
}
function Add-Field([string]$Caption, [int]$Y, [bool]$Browse = $false) {
    $null = Add-Label $Caption 16 ($Y + 3) 173
    $box = New-Object Windows.Forms.TextBox
    $width = if ($Browse) { 321 } else { 410 }
    $box.SetBounds(192, $Y, $width, 27)
    $form.Controls.Add($box)
    if ($Browse) {
        $button = Add-Button 'Browse...' 521 ($Y - 2) 81
        $button.Tag = $box
        $box.Add_EnabledChanged({ param($sender, $eventArgs) $sender.Tag.Enabled = $sender.Enabled })
        $box.Tag = $button
        $button.Add_Click({
            param($sender, $eventArgs)
            $picker = New-Object Windows.Forms.OpenFileDialog
            try {
                $picker.Filter = 'Windows executables (*.exe)|*.exe'
                if ($picker.ShowDialog($form) -eq 'OK') { $sender.Tag.Text = $picker.FileName }
            } finally { $picker.Dispose() }
        })
    }
    $box
}

$null = Add-Label 'Rubies of Eventide' 16 15
$null = Add-Label 'Session' 16 53 173
$modePicker = New-Object Windows.Forms.ComboBox
$modePicker.DropDownStyle = 'DropDownList'
$modePicker.SetBounds(192, 50, 190, 27)
$modePicker.Items.AddRange(@('Local', 'Public'))
$form.Controls.Add($modePicker)
$fields = [ordered]@{
    Endpoint = Add-Field 'Login address' 89
    Server = Add-Field 'Game server executable' 124 $true
    Arguments = Add-Field 'Server arguments' 159
    ReadyPort = Add-Field 'Local TCP port (optional)' 194
    Cloudflared = Add-Field 'Cloudflared (optional)' 229 $true
    Tunnel = Add-Field 'Cloudflare tunnel name' 264
}
$note = Add-Label '' 16 301
$hostButton = Add-Button 'Host and play' 16 331 155
$joinButton = Add-Button 'Open game client' 180 331 145
$resetButton = Add-Button 'Restore original login' 334 331 175
$accountButton = Add-Button 'Accounts' 518 331 85
$accountButton.Add_Click({ Show-RoeAccounts })
$builderButton = Add-Button 'Character Builder' 16 371 155
$builderButton.Add_Click({
    try {
        $install = Split-Path -Parent (Find-GameClient)
        $builder = Resolve-Executable (Join-Path $install 'CharacterBuilder.exe')
        $null = Start-Component $builder ''
        $status.Text = 'Character Builder opened.'
    } catch { Show-Error $_ }
})
$status = Add-Label '' 16 416

$script:currentMode = ''
$running = @{}
function Save-Profile {
    if (-not $script:currentMode) { return }
    foreach ($name in $fields.Keys) {
        $profiles[$script:currentMode].$name = $fields[$name].Text.Trim()
    }
    $temp = "$settingsFile.tmp"
    $profiles | ConvertTo-Json | Set-Content -LiteralPath $temp -Encoding UTF8
    Move-Item -LiteralPath $temp -Destination $settingsFile -Force
}
function Update-Mode {
    $script:currentMode = [string]$modePicker.SelectedItem
    foreach ($name in $fields.Keys) { $fields[$name].Text = $profiles[$script:currentMode].$name }
    $isPublic = $script:currentMode -eq 'Public'
    $fields.Cloudflared.Enabled = $isPublic
    $fields.Tunnel.Enabled = $isPublic
    $note.Text = if ($isPublic) { 'Use your public game endpoint or a configured Cloudflare Spectrum endpoint.' }
        else { 'Use 127.0.0.1 for solo, or a LAN address for friends on your network.' }
}
function Invoke-Play([bool]$HostGame) {
    if (Get-Process -Name Lithtech -ErrorAction SilentlyContinue) { throw 'Close the running game before switching or launching a session.' }
    $clientPath = Find-GameClient
    Save-Profile
    $profile = $profiles[$script:currentMode]
    $serverPath = $null
    $connector = $null
    $port = 0
    if ($HostGame) {
        if (-not $profile.Server) { throw 'Choose a compatible Rubies of Eventide game server executable first. The game install contains the client.' }
        $serverPath = Resolve-Executable $profile.Server
        if ((Split-Path -Leaf $serverPath) -in 'Rubies.exe', 'RubiesLauncher.exe', 'Lithtech.exe', 'CharacterBuilder.exe') {
            throw 'Select a compatible game server executable. The installed updater, launcher, client, and Character Builder cannot host the game.'
        }
        if ($profile.ReadyPort -and (-not [int]::TryParse($profile.ReadyPort, [ref]$port) -or $port -lt 1 -or $port -gt 65535)) {
            throw 'Enter a local TCP port from 1 to 65535, or leave it blank.'
        }
        if ($script:currentMode -eq 'Public' -and ($profile.Cloudflared -or $profile.Tunnel)) {
            $connector = Resolve-Executable $profile.Cloudflared
            if ($profile.Tunnel -notmatch '^[a-zA-Z0-9_-]+$') { throw 'Enter the configured Cloudflare tunnel name or ID.' }
        }
        foreach ($session in $running.Values) {
            if ($session.Mode -ne $script:currentMode -and -not $session.Server.HasExited) {
                throw "Close the $($session.Mode) server console before hosting the other profile."
            }
        }
    }
    Set-LoginServer $profile.Endpoint
    if ($HostGame) {
        $session = $running[$script:currentMode]
        if ($null -eq $session -or $session.Server.HasExited) {
            $session = [pscustomobject]@{
                Mode = $script:currentMode
                Server = (Start-Component $serverPath $profile.Arguments)
                Path = $serverPath
                Arguments = $profile.Arguments
                Tunnel = $null
                TunnelCommand = ''
            }
            $running[$script:currentMode] = $session
        } elseif ($session.Path -ne $serverPath -or $session.Arguments -ne $profile.Arguments) {
            throw 'Close the current server console before changing its executable or arguments.'
        }
        $status.Text = 'Waiting for the game server...'
        $status.Refresh()
        Wait-ForServer $session.Server $port
        if ($connector) {
            $tunnelCommand = "tunnel run $($profile.Tunnel)"
            if ($null -eq $session.Tunnel -or $session.Tunnel.HasExited) {
                $session.Tunnel = Start-Component $connector $tunnelCommand
                $session.TunnelCommand = "$connector $tunnelCommand"
            } elseif ($session.TunnelCommand -ne "$connector $tunnelCommand") {
                throw 'Close the current Cloudflare connector console before changing tunnels.'
            }
            if ($session.Tunnel.WaitForExit(1200)) { throw 'Cloudflared exited during startup. Check its configuration.' }
        }
    }
    $null = Start-Component $clientPath '-rez engine.rez -rez rez +windowed 0'
    $status.Text = "Game launched for $($profile.Endpoint)."
}
function Show-Error($Failure) {
    $status.Text = 'Action could not be completed.'
    $null = [Windows.Forms.MessageBox]::Show($form, $Failure.Exception.Message, 'ROE:MOD', 'OK', 'Warning')
}

$modePicker.Add_SelectedIndexChanged({ try { Save-Profile; Update-Mode } catch { Show-Error $_ } })
$hostButton.Add_Click({ try { Invoke-Play $true } catch { Show-Error $_ } })
$joinButton.Add_Click({ try { Invoke-Play $false } catch { Show-Error $_ } })
$resetButton.Add_Click({
    try {
        if (Get-Process -Name Lithtech -ErrorAction SilentlyContinue) { throw 'Close the game before changing its login address.' }
        Set-LoginServer 'phoenix.jihadmud.com'
        $status.Text = 'Original login address restored.'
    } catch { Show-Error $_ }
})
$form.Add_FormClosing({ param($sender, $eventArgs) try { Save-Profile } catch { Show-Error $_; $eventArgs.Cancel = $true } })
$modePicker.SelectedIndex = 0
$form.Add_Shown({ Show-RoeAccounts })
[void]$form.ShowDialog()





