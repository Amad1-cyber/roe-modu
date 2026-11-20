$accountFile = Join-Path $PSScriptRoot 'accounts.json'

function Read-RoeAccounts {
    if (Test-Path -LiteralPath $accountFile) {
        foreach ($entry in (Get-Content -LiteralPath $accountFile -Raw | ConvertFrom-Json)) { $entry }
    }
}
function Get-RoePasswordHash([string]$Password, [byte[]]$Salt) {
    $derive = [Security.Cryptography.Rfc2898DeriveBytes]::new($Password, $Salt, 600000, [Security.Cryptography.HashAlgorithmName]::SHA256)
    try { [Convert]::ToBase64String($derive.GetBytes(32)) } finally { $derive.Dispose() }
}
function Add-RoeAccount([string]$Name, [string]$Password, [ValidateSet('Player','Administrator')][string]$Role = 'Player') {
    if ($Name -notmatch '^[a-zA-Z0-9_-]{3,24}$') { throw 'Use 3 to 24 letters, digits, underscores or hyphens for the username.' }
    if ($Role -eq 'Player' -and $Password.Length -lt 8) { throw 'Use at least eight characters for a player password.' }

    $lock = [IO.File]::Open("$accountFile.lock", 'OpenOrCreate', 'ReadWrite', 'None')
    try {
        $accounts = @(Read-RoeAccounts)
        if ($accounts | Where-Object Name -eq $Name) { throw 'That username is already taken.' }
        $salt = New-Object byte[] 16
        $random = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $random.GetBytes($salt) } finally { $random.Dispose() }
        $accounts += [pscustomobject]@{
            Name = $Name
            Role = $Role
            Salt = [Convert]::ToBase64String($salt)
            Hash = Get-RoePasswordHash $Password $salt
        }
        $temp = "$accountFile.tmp"
        [IO.File]::WriteAllText($temp, (ConvertTo-Json -InputObject $accounts -Depth 3))
        if ([IO.File]::Exists($accountFile)) {
            [IO.File]::Replace($temp, $accountFile, "$accountFile.bak")
            [IO.File]::Delete("$accountFile.bak")
        }
        else { [IO.File]::Move($temp, $accountFile) }
    } finally { $lock.Dispose() }
}
function Get-RoeAccount([string]$Name, [string]$Password) {
    $account = Read-RoeAccounts | Where-Object Name -eq $Name | Select-Object -First 1
    if ($null -eq $account -or (Get-RoePasswordHash $Password ([Convert]::FromBase64String($account.Salt))) -cne $account.Hash) {
        throw 'Incorrect username or password.'
    }
    [pscustomobject]@{ Name = $account.Name; Role = $account.Role }
}

function Show-RoeAccounts {
    $dialog = New-Object Windows.Forms.Form
    $dialog.Text = 'ROE:MOD local launcher accounts'
    $dialog.ClientSize = New-Object Drawing.Size(450, 265)
    $dialog.BackColor = [Drawing.Color]::FromArgb(29, 27, 36)
    $dialog.ForeColor = [Drawing.Color]::FromArgb(242, 237, 231)
    $dialog.Font = New-Object Drawing.Font('Segoe UI', 10)
    $heading = New-Object Windows.Forms.Label
    $heading.Text = 'ROE:MOD'
    $heading.Font = New-Object Drawing.Font('Segoe UI', 23, [Drawing.FontStyle]::Bold)
    $heading.ForeColor = [Drawing.Color]::FromArgb(238, 173, 120)
    $heading.SetBounds(14, 9, 418, 45)
    $subheading = New-Object Windows.Forms.Label
    $subheading.Text = 'Local launcher sign-in'
    $subheading.SetBounds(18, 55, 410, 25)
    $dialog.StartPosition = 'CenterParent'
    $dialog.FormBorderStyle = 'FixedDialog'
    $dialog.MaximizeBox = $false
    $dialog.MinimizeBox = $false
    $nameLabel = New-Object Windows.Forms.Label
    $nameLabel.Text = 'Username'
    $nameLabel.SetBounds(18, 94, 95, 22)
    $nameBox = New-Object Windows.Forms.TextBox
    $nameBox.SetBounds(118, 92, 312, 24)
    $passLabel = New-Object Windows.Forms.Label
    $passLabel.Text = 'Password'
    $passLabel.SetBounds(18, 128, 95, 22)
    $passBox = New-Object Windows.Forms.TextBox
    $passBox.UseSystemPasswordChar = $true
    $passBox.SetBounds(118, 126, 312, 24)
    $signIn = New-Object Windows.Forms.Button
    $signIn.Text = 'Sign in'
    $signIn.SetBounds(118, 165, 96, 35)
    $create = New-Object Windows.Forms.Button
    $create.Text = 'Create player account'
    $create.SetBounds(225, 165, 205, 35)
    $result = New-Object Windows.Forms.Label
    $result.SetBounds(18, 214, 412, 45)
    $result.Text = 'These accounts are stored on this PC for the launcher.'
    $signIn.Add_Click({
        try {
            $account = Get-RoeAccount $nameBox.Text.Trim() $passBox.Text
            
            $accountButton.Text = $account.Name
            $result.Text = "Signed in as $($account.Name) ($($account.Role))."
        } catch { $result.Text = $_.Exception.Message }
        finally { $passBox.Clear() }
    })
    foreach ($button in $signIn, $create) {
        $button.FlatStyle = 'Flat'
        $button.BackColor = [Drawing.Color]::FromArgb(63, 48, 63)
    }
    $create.Add_Click({
        try {
            Add-RoeAccount $nameBox.Text.Trim() $passBox.Text
            $result.Text = 'Player account created. Enter your password to sign in.'
        } catch { $result.Text = $_.Exception.Message }
        finally { $passBox.Clear() }
    })
    $dialog.Controls.AddRange(@($heading, $subheading, $nameLabel, $nameBox, $passLabel, $passBox, $signIn, $create, $result))
    $dialog.AcceptButton = $signIn
    try { [void]$dialog.ShowDialog($form) } finally { $dialog.Dispose() }
}


