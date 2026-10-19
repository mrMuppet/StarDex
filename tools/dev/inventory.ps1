<#
  Phase 3: Asset-Inventarisierung eines app0-Dumps.
  Aufruf:  powershell -ExecutionPolicy Bypass -File tools\inventory.ps1 -Root D:\dump\app0 [-Out .\analysis]
  Erzeugt: files.csv, extensions.txt, magic.txt, hexdumps.txt, ffprobe.txt
#>
param(
    [Parameter(Mandatory)] [string]$Root,
    [string]$Out = (Join-Path $PSScriptRoot '..\analysis'),
    [int]$HexBytes = 256,
    [int]$SamplesPerExt = 2
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force $Out | Out-Null
$rootFull = (Resolve-Path $Root).Path.TrimEnd('\')
$files = Get-ChildItem -LiteralPath $rootFull -Recurse -File

function Get-Head([string]$path, [int]$n) {
    $fs = [IO.File]::OpenRead($path)
    try { $buf = New-Object byte[] ([Math]::Min($n, $fs.Length)); [void]$fs.Read($buf, 0, $buf.Length); $buf }
    finally { $fs.Dispose() }
}

# Shannon-Entropie (bit/byte) der ersten 64 KiB: ~8.0 = verschluesselt/komprimiert, <6 = Klartext/Strukturdaten
function Get-Entropy([byte[]]$b) {
    if ($b.Length -eq 0) { return 0 }
    $c = New-Object int[] 256; foreach ($x in $b) { $c[$x]++ }
    $h = 0.0; foreach ($k in $c) { if ($k) { $p = $k / $b.Length; $h -= $p * [Math]::Log($p, 2) } }
    [Math]::Round($h, 2)
}

# 1. Dateiliste
$rows = foreach ($f in $files) {
    $head = Get-Head $f.FullName 65536
    [pscustomobject]@{
        Path    = $f.FullName.Substring($rootFull.Length + 1)
        Size    = $f.Length
        Ext     = $f.Extension.ToLower()
        Magic   = (($head | Select-Object -First 8 | ForEach-Object { $_.ToString('X2') }) -join ' ')
        Ascii   = -join ($head | Select-Object -First 8 | ForEach-Object { if ($_ -ge 32 -and $_ -lt 127) { [char]$_ } else { '.' } })
        Entropy = Get-Entropy $head
    }
}
$rows | Sort-Object Path | Export-Csv (Join-Path $Out 'files.csv') -NoTypeInformation -Encoding UTF8

# 2. Endungs-Uebersicht
$rows | Group-Object Ext | Sort-Object Count -Descending | ForEach-Object {
    $sum = ($_.Group | Measure-Object Size -Sum).Sum
    '{0,-12} {1,6} Dateien {2,12:N0} KB   avg-Entropie {3:N2}' -f ($(if ($_.Name) { $_.Name } else { '(keine)' })), $_.Count, ($sum / 1KB), (($_.Group | Measure-Object Entropy -Average).Average)
} | Set-Content (Join-Path $Out 'extensions.txt') -Encoding UTF8

# Magic-Byte-Gruppen (Endungen luegen oft, Magic nicht)
$rows | Group-Object Magic | Sort-Object Count -Descending | ForEach-Object {
    '{0}  |{1}|  {2,5}x  z.B. {3}' -f $_.Name, $_.Group[0].Ascii, $_.Count, $_.Group[0].Path
} | Set-Content (Join-Path $Out 'magic.txt') -Encoding UTF8

# 3./4. Hexdumps + ffprobe fuer Stichproben je Endung
$xxd = Get-Command xxd -ErrorAction SilentlyContinue
$ffprobe = Get-Command ffprobe -ErrorAction SilentlyContinue
$mediaExt = '.at9', '.mp4', '.m4a', '.wav', '.vag', '.ogg', '.mp3', '.bik', '.webm', '.mov', '.aac', '.adx'
$hexOut = Join-Path $Out 'hexdumps.txt'; $ffOut = Join-Path $Out 'ffprobe.txt'
Remove-Item $hexOut, $ffOut -ErrorAction SilentlyContinue

foreach ($g in ($rows | Group-Object Ext)) {
    foreach ($r in ($g.Group | Sort-Object Size | Select-Object -First $SamplesPerExt)) {
        $full = Join-Path $rootFull $r.Path
        Add-Content $hexOut "===== $($r.Path)  ($($r.Size) bytes, entropy $($r.Entropy))" -Encoding UTF8
        if ($xxd) { & $xxd.Source -l $HexBytes $full | Add-Content $hexOut -Encoding UTF8 }
        else { Format-Hex -Path $full | Select-Object -First ($HexBytes / 16) | Out-String | Add-Content $hexOut -Encoding UTF8 }
        if ($ffprobe -and ($mediaExt -contains $r.Ext -or $r.Ascii -match 'ftyp|RIFF|OggS|ID3')) {
            Add-Content $ffOut "===== $($r.Path)" -Encoding UTF8
            $o = & $ffprobe.Source -hide_banner -show_streams -show_format $full 2>&1 | Out-String
            Add-Content $ffOut $o -Encoding UTF8
        }
    }
}

"Fertig: $($files.Count) Dateien -> $((Resolve-Path $Out).Path)"
