!macro NSIS_HOOK_POSTINSTALL
  ; Refresh active Add/Remove Programs metadata after in-place upgrades.
  WriteRegStr SHCTX "${UNINSTKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr SHCTX "${UNINSTKEY}" "InstallLocation" "$\"$INSTDIR$\""
  WriteRegStr SHCTX "${UNINSTKEY}" "UninstallString" "$\"$INSTDIR\uninstall.exe$\""
  WriteRegStr SHCTX "${UNINSTKEY}" "DisplayIcon" "$\"$INSTDIR\${MAINBINARYNAME}.exe$\""
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; Runtime bootstrap files belong to the application.
  RMDir /r "$INSTDIR\resources"
  RMDir "$INSTDIR"
!macroend
