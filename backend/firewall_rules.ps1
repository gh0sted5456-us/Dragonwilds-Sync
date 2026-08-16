param(
    [ValidateSet('Query','Ensure','Remove')][string]$Action = 'Query',
    [ValidatePattern('^Dragonwilds Sync - [A-Za-z0-9 .:_-]{1,160}$')][string]$DisplayName,
    [ValidateSet('Dragonwilds Sync')][string]$Group = 'Dragonwilds Sync',
    [ValidateSet('Inbound','Outbound')][string]$Direction = 'Inbound',
    [ValidateSet('TCP','UDP')][string]$Protocol = 'TCP',
    [ValidateRange(1,65535)][int]$LocalPort,
    [string]$Program = '',
    [ValidateSet('Any','Domain,Private')][string]$Profiles = 'Any',
    [ValidateSet('Any','LocalSubnet')][string]$RemoteAddress = 'Any',
    [switch]$ElevatedChild
)

$ErrorActionPreference = 'Stop'

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if ($Action -ne 'Query' -and -not (Test-Administrator)) {
    if ($ElevatedChild) { throw 'Firewall elevation was not granted.' }
    $arguments = @(
        '-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $PSCommandPath + '"'),
        '-Action',$Action,'-DisplayName',('"' + $DisplayName + '"'),'-Group',('"' + $Group + '"'),
        '-Direction',$Direction,'-Protocol',$Protocol,'-LocalPort',[string]$LocalPort,
        '-Program',('"' + $Program + '"'),'-Profiles',$Profiles,'-RemoteAddress',$RemoteAddress,'-ElevatedChild'
    )
    $process = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -WindowStyle Hidden -ArgumentList $arguments
    exit $process.ExitCode
}

$existing = @(Get-NetFirewallRule -Group $Group -DisplayName $DisplayName -ErrorAction SilentlyContinue)
if ($Action -eq 'Query') {
    $existing | ForEach-Object {
        $port = $_ | Get-NetFirewallPortFilter
        $address = $_ | Get-NetFirewallAddressFilter
        $app = $_ | Get-NetFirewallApplicationFilter
        [pscustomobject]@{
            DisplayName=$_.DisplayName; Group=$_.Group; Enabled=[string]$_.Enabled;
            Direction=[string]$_.Direction; Profiles=[string]$_.Profile;
            Protocol=[string]$port.Protocol; LocalPort=[string]$port.LocalPort;
            Program=[string]$app.Program; LocalAddress=[string]$address.LocalAddress;
            RemoteAddress=[string]$address.RemoteAddress
        }
    } | ConvertTo-Json -Compress
    exit 0
}

if ($Action -eq 'Remove') {
    $existing | Remove-NetFirewallRule
    Write-Output 'Owned firewall rule removed.'
    exit 0
}

$profileValue = if ($Profiles -eq 'Any') { 'Any' } else { @('Domain','Private') }
$programValue = if ([string]::IsNullOrWhiteSpace($Program)) { 'Any' } else { $Program }
$correct = $false
if ($existing.Count -eq 1) {
    $rule = $existing[0]
    $portFilter = $rule | Get-NetFirewallPortFilter
    $addressFilter = $rule | Get-NetFirewallAddressFilter
    $appFilter = $rule | Get-NetFirewallApplicationFilter
    $actualProfiles = [string]$rule.Profile
    $profileCorrect = if ($Profiles -eq 'Any') { $actualProfiles -eq 'Any' } else {
        $actualProfiles -match 'Domain' -and $actualProfiles -match 'Private' -and $actualProfiles -notmatch 'Public'
    }
    $correct = ([string]$rule.Direction -eq $Direction) -and ([string]$portFilter.Protocol -eq $Protocol) -and
        ([string]$portFilter.LocalPort -eq [string]$LocalPort) -and
        $profileCorrect -and ([string]$addressFilter.LocalAddress -eq 'Any') -and
        ([string]$addressFilter.RemoteAddress -eq $RemoteAddress) -and
        (($programValue -eq 'Any' -and [string]$appFilter.Program -eq 'Any') -or ([string]$appFilter.Program -eq $programValue))
}
if ($correct) {
    Write-Output 'Owned firewall rule already correct.'
    exit 0
}
$existing | Remove-NetFirewallRule
$parameters = @{
    DisplayName=$DisplayName; Group=$Group; Direction=$Direction; Action='Allow'; Enabled='True';
    Profile=$profileValue; Protocol=$Protocol; LocalPort=$LocalPort;
    LocalAddress='Any'; RemoteAddress=$RemoteAddress
}
if ($programValue -ne 'Any') { $parameters.Program = $programValue }
New-NetFirewallRule @parameters | Out-Null
Write-Output 'Owned firewall rule created or repaired.'
