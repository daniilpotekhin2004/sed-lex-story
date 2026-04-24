from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_legal_concept_service
from app.schemas.legal import LegalConceptCreate, LegalConceptList, LegalConceptRead
from app.services.legal import LegalConceptService

router = APIRouter(prefix="/v1/legal", tags=["legal"])


@router.post("", response_model=LegalConceptRead, status_code=status.HTTP_201_CREATED)
async def create_legal_concept(
    payload: LegalConceptCreate,
    service: LegalConceptService = Depends(get_legal_concept_service),
) -> LegalConceptRead:
    concept = await service.create_concept(payload)
    return concept


@router.get("", response_model=LegalConceptList)
async def list_legal_concepts(
    service: LegalConceptService = Depends(get_legal_concept_service),
) -> LegalConceptList:
    concepts = await service.list_concepts()
    return LegalConceptList(items=concepts)


@router.get("/{concept_id}", response_model=LegalConceptRead)
async def get_legal_concept(
    concept_id: str,
    service: LegalConceptService = Depends(get_legal_concept_service),
) -> LegalConceptRead:
    concept = await service.get_concept(concept_id)
    if concept is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Legal concept not found")
    return concept
