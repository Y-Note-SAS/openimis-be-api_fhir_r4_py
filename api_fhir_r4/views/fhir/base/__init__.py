from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from api_fhir_r4.multiserializer import MultiSerializerSerializerClass
from api_fhir_r4.paginations import FhirBundleResultsSetPagination
from api_fhir_r4.permissions import FHIRApiPermissions
from api_fhir_r4.views import CsrfExemptSessionAuthentication


class BaseFHIRView(APIView):
    pagination_class = FhirBundleResultsSetPagination
    permission_classes = (FHIRApiPermissions,)
    authentication_classes = [CsrfExemptSessionAuthentication] + APIView.settings.DEFAULT_AUTHENTICATION_CLASSES


class BaseMultiserializerFHIRView(BaseFHIRView):
    # The view only requires an authenticated user; the real check is per registered
    # serializer (multiserializer mixins), which refuses when none of them passes.
    # Inheriting FHIRApiPermissions here (v1.7.0) shadowed the mixin's IsAuthenticated.
    permission_classes = (IsAuthenticated,)
    serializer_class = MultiSerializerSerializerClass
