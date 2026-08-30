!macro NSIS_HOOK_POSTUNINSTALL
  ; Runtime bootstrap files belong to the application.
  RMDir /r "$INSTDIR\resources"
  RMDir "$INSTDIR"
!macroend
