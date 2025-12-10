from django.apps import AppConfig

class CmsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cms'

    def ready(self):
        import cms.signals  # 👈 this connects your signals
        self._register_merge_models()

    def _register_merge_models(self) -> None:
        """Ensure merge-enabled models are available to the registry."""

        try:
            from cms.merge import register_merge_rules
            from cms.models import Element, FieldSlip, Reference, Storage
        except ImportError:  # pragma: no cover - defensive import guard
            return

        for model in (FieldSlip, Storage, Reference, Element):
            register_merge_rules(model)
