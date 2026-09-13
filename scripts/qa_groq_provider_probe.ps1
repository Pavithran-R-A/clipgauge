param(
    [ValidateSet(
        'openai/gpt-oss-20b',
        'openai/gpt-oss-120b',
        'qwen/qwen3.8-27b',
        'qwen/qwen3.6-27b'
    )]
    [string]$Model = 'openai/gpt-oss-20b'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$clipgaugeRoot = Join-Path $env:USERPROFILE '.clipgauge'
$python = Join-Path $clipgaugeRoot 'runtimes\pipeline\Scripts\python.exe'

Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class ClipGaugeGroqProbeCredential {
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
    public struct CREDENTIAL {
        public UInt32 Flags; public UInt32 Type; public IntPtr TargetName; public IntPtr Comment;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
        public UInt32 CredentialBlobSize; public IntPtr CredentialBlob; public UInt32 Persist;
        public UInt32 AttributeCount; public IntPtr Attributes; public IntPtr TargetAlias; public IntPtr UserName;
    }
    [DllImport("Advapi32.dll", EntryPoint="CredReadW", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern bool CredRead(string target, UInt32 type, UInt32 flags, out IntPtr credential);
    [DllImport("Advapi32.dll", SetLastError=true)] static extern void CredFree(IntPtr credential);
    public static string Read(string target) {
        IntPtr pointer; if (!CredRead(target, 1, 0, out pointer)) return null;
        try {
            var value = Marshal.PtrToStructure<CREDENTIAL>(pointer);
            if (value.CredentialBlob == IntPtr.Zero || value.CredentialBlobSize == 0) return null;
            var bytes = new byte[value.CredentialBlobSize]; Marshal.Copy(value.CredentialBlob, bytes, 0, bytes.Length);
            return Encoding.Unicode.GetString(bytes).TrimEnd('\0');
        } finally { CredFree(pointer); }
    }
}
"@

$secret = [ClipGaugeGroqProbeCredential]::Read('LegacyGeneric:target=provider_auth_preset-groq.io.github.pavithranra.clipgauge')
if (-not $secret) { throw 'configured Groq credential is unavailable' }
$env:CLIPGAUGE_GROQ_API_KEY = $secret
$env:PYTHONPATH = Join-Path $repoRoot 'pipeline'

try {
    & $python (Join-Path $PSScriptRoot 'qa_groq_provider_probe.py') $Model
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Remove-Item Env:CLIPGAUGE_GROQ_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
}
