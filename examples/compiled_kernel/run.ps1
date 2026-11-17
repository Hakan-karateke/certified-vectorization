# ArcKernel.cs dosyasını Windows'un kendi C# derleyicisiyle derler ve verilen
# klasördeki her *.in dosyası için çalıştırır; süreleri timings.json'a yazar.
param([Parameter(Mandatory = $true)][string]$Folder)
$ErrorActionPreference = 'Stop'

$source = Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot 'ArcKernel.cs')
$options = New-Object System.CodeDom.Compiler.CompilerParameters
$options.CompilerOptions = '/optimize+'
$options.GenerateInMemory = $true
[void]$options.ReferencedAssemblies.Add('System.dll')
Add-Type -TypeDefinition $source -CompilerParameters $options

$timings = @{}
foreach ($file in Get-ChildItem -Path $Folder -Filter '*.in') {
    $out = [System.IO.Path]::ChangeExtension($file.FullName, '.out')
    # İlk çağrı JIT derlemesini içerir; ölçüm ikinci çağrıdan alınır.
    [void][ArcKernel]::Run($file.FullName, $out)
    $timings[$file.BaseName] = [ArcKernel]::Run($file.FullName, $out)
}
$timings | ConvertTo-Json | Out-File -Encoding utf8 (Join-Path $Folder 'timings.json')
"64-bit: $([Environment]::Is64BitProcess); CLR $([Environment]::Version)"
