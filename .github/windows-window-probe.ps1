param(
  [Parameter(Mandatory = $true)] [int] $ProcessId
)

$ErrorActionPreference = 'Stop'
Add-Type @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public static class ClipGaugeNativeWindowProbe {
  private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
  [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int maxCount);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetClassName(IntPtr hWnd, StringBuilder text, int maxCount);
  [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hWnd);

  public static string[] ForProcess(uint targetProcessId) {
    var windows = new List<string>();
    EnumWindows((hWnd, lParam) => {
      uint processId;
      GetWindowThreadProcessId(hWnd, out processId);
      if (processId != targetProcessId || !IsWindowVisible(hWnd)) return true;
      var title = new StringBuilder(512);
      var className = new StringBuilder(256);
      GetWindowText(hWnd, title, title.Capacity);
      GetClassName(hWnd, className, className.Capacity);
      windows.Add(hWnd.ToInt64().ToString() + "|" + title.ToString() + "|" + className.ToString());
      return true;
    }, IntPtr.Zero);
    return windows.ToArray();
  }
}
"@

[ClipGaugeNativeWindowProbe]::ForProcess([uint32]$ProcessId) | ConvertTo-Json -Compress
