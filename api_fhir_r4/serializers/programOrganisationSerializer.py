from django.utils.translation import gettext as _
from rest_framework.exceptions import MethodNotAllowed

from api_fhir_r4.converters.programOrganisationConverter import ProgramOrganisationConverter
from api_fhir_r4.serializers import BaseFHIRSerializer


class ProgramOrganisationSerializer(BaseFHIRSerializer):
    fhirConverter = ProgramOrganisationConverter()

    def create(self, validated_data):
        raise MethodNotAllowed('POST', detail=_('Programs are read-only, write operations are not supported.'))

    def update(self, instance, validated_data):
        raise MethodNotAllowed('PUT', detail=_('Programs are read-only, write operations are not supported.'))
