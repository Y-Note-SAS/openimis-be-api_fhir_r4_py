from api_fhir_r4.converters.planDefinitionConverter import PlanDefinitionConverter
from api_fhir_r4.serializers import BaseFHIRSerializer


class PlanDefinitionSerializer(BaseFHIRSerializer):
    fhirConverter = PlanDefinitionConverter()
