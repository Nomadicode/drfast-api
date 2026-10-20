Fields and files
================

Optional model fields live outside the core install. Add the extras you use:

.. code-block:: bash

   pip install "drfast-api[encryption]"   # EncryptedCharField
   pip install "drfast-api[images]"       # ImageField (Pillow)
   pip install "drfast-api[s3]"           # S3-compatible storage (boto3)
   pip install "drfast-api[files]"        # images + s3

Encrypted text
--------------

:class:`drfast.fields.EncryptedCharField` stores a string encrypted with Fernet.
``max_length`` limits the plaintext; the column is ``TEXT`` because the ciphertext
is several times longer.

.. code-block:: python

   from drfast.fields import EncryptedCharField

   class Connection(Model):
       access_token = EncryptedCharField(max_length=2048)

Set ``ENCRYPTION_KEY`` to a Fernet key. To rotate, prepend the new key with a
comma (``ENCRYPTION_KEY=new,old``): the first key encrypts and every key decrypts.
Without a key one is derived from ``SECRET_KEY``. Values written before a column
was encrypted are returned unchanged, so a plain column can be converted in place.

Files and images
----------------

:class:`drfast.files.FileField` and :class:`drfast.files.ImageField` store the
name of a file kept in a :class:`drfast.storage.Storage`. Models that use them
inherit :class:`drfast.files.FileModelMixin`, which uploads assigned files when the
model is saved:

.. code-block:: python

   from drfast.files import FileModelMixin, ImageField, FileField
   from drfast.storage import private_storage

   class Merchant(FileModelMixin, Model):
       logo = ImageField(upload_to="logos/%Y/%m/", null=True)
       tax_document = FileField(upload_to=document_path, storage=private_storage, null=True)

   merchant.logo = upload_file          # a FastAPI UploadFile or a ContentFile
   await merchant.save()
   merchant.logo.url

``upload_to`` is a directory (``strftime`` tokens allowed) or a callable
``(instance, filename) -> name``. Client file names are reduced to a safe base
name, and an existing file is never overwritten. ``ImageField`` rejects content
Pillow does not recognise as an image. Storage choices are not written into
migrations, so the backend can change without a schema change.

Render a file field as its URL with the read-only ``drfast.FileField`` serializer
field.

Storage
-------

``public_storage()`` holds files anyone may read; ``private_storage()`` holds
files behind signed URLs that expire after ``PRIVATE_URL_EXPIRE_SECONDS``. Both
follow the settings:

* ``STORAGE_BACKEND=filesystem`` (default) writes under ``MEDIA_ROOT``. Nothing
  serves that directory, so private files stay private in development.
* ``STORAGE_BACKEND=s3`` targets any S3-compatible service through the
  ``AWS_*`` settings. ``AWS_PRIVATE_STORAGE_BUCKET_NAME`` must differ from
  ``AWS_STORAGE_BUCKET_NAME``: services such as Cloudflare R2 have no object
  ACLs, so a shared bucket with a public domain would expose private files. Leave
  ``AWS_DEFAULT_ACL`` empty on R2.

Subclass :class:`drfast.storage.Storage` for any other backend.
