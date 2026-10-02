from rest_framework import viewsets

from api_fhir_r4.permissions import FHIRApiPlanDefinitionPermissions
from api_fhir_r4.serializers import PlanDefinitionSerializer
from api_fhir_r4.views.fhir.base import BaseFHIRView


class PlanDefinitionViewSet(BaseFHIRView, viewsets.ReadOnlyModelViewSet):
    """
    CSU specific endpoint.

    Exposes the openIMIS CSU programs as read-only FHIR R4 PlanDefinition
    resources.
    """

    serializer_class = PlanDefinitionSerializer
    permission_classes = (FHIRApiPlanDefinitionPermissions,)
    lookup_field = 'idProgram'

    def get_queryset(self):
        # Imported lazily: the program module is only installed on CSU instances.
        from program.models import Program
        return Program.objects.all().order_by('idProgram')
