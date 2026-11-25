import pytest
from crum import impersonate, set_current_user
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from cms.models import Reference, ReferenceDocument


User = get_user_model()


@pytest.fixture
def collection_manager(db):
    user = User.objects.create_user(username="reference-document-manager")
    group, _ = Group.objects.get_or_create(name="Collection Managers")
    user.groups.add(group)
    set_current_user(user)
    try:
        yield user
    finally:
        set_current_user(None)


@pytest.fixture
def reference(collection_manager):
    return Reference.objects.create(
        title="Reference document test",
        first_author="A. Author",
        year="2024",
        citation="Author 2024",
    )


def pdf_upload(name="paper.pdf", content=b"%PDF-1.7\nPDF content"):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


def test_collection_manager_can_upload_pdf_to_reference(
    client, collection_manager, reference, tmp_path
):
    client.force_login(collection_manager)

    with override_settings(MEDIA_ROOT=tmp_path):
        response = client.post(
            reverse("reference_upload_document", args=[reference.pk]),
            {"file": pdf_upload()},
        )

        assert response.status_code == 302
        document = ReferenceDocument.objects.get(reference=reference)
        assert document.original_filename == "paper.pdf"
        assert document.file.name.startswith(
            f"uploads/references/{reference.pk}/"
        )
        stored_file = tmp_path / document.file.name
        assert stored_file.is_file()

        with impersonate(collection_manager):
            document.delete()
        assert not stored_file.exists()


def test_reference_document_folder_is_removed_after_its_last_file_is_deleted(
    collection_manager, reference, tmp_path
):
    with override_settings(MEDIA_ROOT=tmp_path):
        first_document = ReferenceDocument.objects.create(
            reference=reference,
            file=pdf_upload("first.pdf"),
        )
        last_document = ReferenceDocument.objects.create(
            reference=reference,
            file=pdf_upload("last.pdf"),
        )
        document_folder = (tmp_path / first_document.file.name).parent

        with impersonate(collection_manager):
            first_document.delete()

        assert document_folder.is_dir()
        assert (tmp_path / last_document.file.name).is_file()

        with impersonate(collection_manager):
            last_document.delete()

        assert not document_folder.exists()


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("paper.txt", b"%PDF-1.7\nnot a PDF extension"),
        ("paper.pdf", b"not a PDF"),
    ],
)
def test_upload_rejects_non_pdf_files(
    client, collection_manager, reference, name, content
):
    client.force_login(collection_manager)

    response = client.post(
        reverse("reference_upload_document", args=[reference.pk]),
        {"file": pdf_upload(name=name, content=content)},
    )

    assert response.status_code == 200
    assert "file" in response.context["form"].errors
    assert not ReferenceDocument.objects.filter(reference=reference).exists()


def test_non_manager_cannot_upload_reference_document(client, reference):
    user = User.objects.create_user(username="reference-document-reader")
    client.force_login(user)

    response = client.post(
        reverse("reference_upload_document", args=[reference.pk]),
        {"file": pdf_upload()},
    )

    assert response.status_code == 302
    assert not ReferenceDocument.objects.filter(reference=reference).exists()


def test_reference_detail_lists_documents_without_preview_or_license(
    client, collection_manager, reference, tmp_path
):
    with override_settings(MEDIA_ROOT=tmp_path):
        document = ReferenceDocument.objects.create(
            reference=reference,
            file=pdf_upload(),
        )
        client.force_login(collection_manager)

        response = client.get(reverse("reference_detail", args=[reference.pk]))

        assert response.status_code == 200
        content = response.content.decode()
        assert (
            f'href="{document.file.url}" target="_blank" rel="noopener"' in content
        )
        assert "paper.pdf" in content
        assert "Upload PDF" in content
        assert "Preview" not in content
        assert "License" not in content
        assert (
            content.index('id="reference-publication-heading"')
            < content.index('id="reference-documents-heading"')
            < content.index('id="reference-accessions-heading"')
        )

        document.file.delete(save=False)


def test_reference_admin_includes_document_upload_inline(
    client, reference
):
    admin_user = User.objects.create_superuser(
        username="reference-document-admin",
        email="reference-document-admin@example.com",
        password="password",
    )
    client.force_login(admin_user)
    response = client.get(
        reverse("admin:cms_reference_change", args=[reference.pk])
    )

    assert response.status_code == 200
    inline_formsets = response.context["inline_admin_formsets"]
    assert any(
        inline.opts.model is ReferenceDocument for inline in inline_formsets
    )
