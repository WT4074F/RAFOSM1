# SPDX-License-Identifier: GPL-2.0-or-later
<#
.SYNOPSIS
  Create a VirtualBox VM set up for installing the OS from a built ISO.

.EXAMPLE
  .\New-DevVM.ps1 -Iso "$HOME\Downloads\ashwood-0.1-i386-Release-abc1234.iso"

.NOTES
  Uses hardware ReactOS supports best: 32-bit, IDE (PIIX4) disk and CD, PCnet-FAST III network,
  AC97 sound, VBoxVGA graphics. It never deletes an existing VM: if the name is taken it stops
  and tells you, unless you pass -Replace (which asks you to confirm first).
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [Parameter(Mandatory = $true)][string]$Iso,
    [string]$Name = 'Ashwood-dev',
    [int]$MemoryMB = 1024,
    [int]$DiskGB = 20,
    [switch]$Replace,
    [switch]$Start
)
$ErrorActionPreference = 'Stop'

$vbox = Get-Command VBoxManage -ErrorAction SilentlyContinue
if (-not $vbox) {
    $guess = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe'
    if (Test-Path $guess) { $vbox = $guess } else { throw 'VBoxManage not found. Is VirtualBox installed?' }
} else { $vbox = $vbox.Source }

function VBox { & $vbox @args; if ($LASTEXITCODE) { throw "VBoxManage $($args -join ' ') failed ($LASTEXITCODE)" } }

$Iso = (Resolve-Path $Iso).Path

$existing = & $vbox list vms | Where-Object { $_ -match "^`"$([regex]::Escape($Name))`"" }
if ($existing) {
    if (-not $Replace) {
        throw "A VM called '$Name' already exists. Use -Name for a different one, or -Replace to delete it and its disk."
    }
    if ($PSCmdlet.ShouldProcess($Name, 'Delete existing VM and its disk')) {
        & $vbox controlvm $Name poweroff 2>$null | Out-Null
        VBox unregistervm $Name --delete
    } else { return }
}

VBox createvm --name $Name --ostype WindowsXP --register
$cfgDir = Split-Path (( & $vbox showvminfo $Name --machinereadable | Select-String '^CfgFile=' ) -replace '^CfgFile="(.*)"$', '$1')
$disk = Join-Path $cfgDir "$Name.vdi"

VBox modifyvm $Name --memory $MemoryMB --vram 32 --cpus 1 --ioapic on --acpi on `
    --graphicscontroller vboxvga --audio-driver default --audio-controller ac97 --audio-enabled on `
    --nic1 nat --nictype1 Am79C973 --boot1 dvd --boot2 disk --boot3 none --boot4 none `
    --mouse ps2 --keyboard ps2 --rtcuseutc off --uart1 0x3F8 4 --uartmode1 file (Join-Path $cfgDir 'serial.log')

VBox createmedium disk --filename $disk --size ($DiskGB * 1024) --format VDI
VBox storagectl $Name --name IDE --add ide --controller PIIX4 --bootable on
VBox storageattach $Name --storagectl IDE --port 0 --device 0 --type hdd --medium $disk
VBox storageattach $Name --storagectl IDE --port 1 --device 0 --type dvddrive --medium $Iso

Write-Host "Created VM '$Name' with $MemoryMB MB RAM and a $DiskGB GB disk, booting from:`n  $Iso"
Write-Host "Kernel debug output (Debug builds) goes to: $(Join-Path $cfgDir 'serial.log')"
if ($Start) { VBox startvm $Name --type gui }
else { Write-Host "Start it with:  VBoxManage startvm `"$Name`"   (or from the VirtualBox window)" }
