param(
  [Parameter(Mandatory = $true)] [long] $WindowHandle,
  [Parameter(Mandatory = $true)] [string] $AutomationId
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$WindowHandle)
if ($null -eq $root) { throw "native window not found: $WindowHandle" }
$condition = New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::AutomationIdProperty,
  $AutomationId
)
$element = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
if ($null -eq $element) { throw "native UIA element not found: $AutomationId" }

$text = ''
$method = 'uia-name'
try {
  $pattern = $element.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
  $text = $pattern.DocumentRange.GetText(-1)
  if (-not [string]::IsNullOrWhiteSpace($text)) { $method = 'uia-textpattern' }
} catch {}
if ([string]::IsNullOrWhiteSpace($text)) { $text = $element.Current.Name }
if ([string]::IsNullOrWhiteSpace($text)) { throw "native UIA element had no readable text: $AutomationId" }

[ordered]@{
  text = $text
  method = $method
  automation_id = $element.Current.AutomationId
  control_type = $element.Current.ControlType.ProgrammaticName
} | ConvertTo-Json -Compress
