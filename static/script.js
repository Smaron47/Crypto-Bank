document.addEventListener('DOMContentLoaded', () => {
  const addBtn = document.getElementById('add-btn');
  const modal = document.getElementById('product-modal');
  const pmForm = document.getElementById('product-form');
  const pmCancel = document.getElementById('pm_cancel');
  const pmTitleHeader = document.getElementById('pm_title_header');
  const pmId = document.getElementById('pm_id');
  const imagesInput = document.getElementById('pm_images');
  const imagesPreview = document.getElementById('pm_images_preview');

  // simple Quill init (if using)
  const quill = new Quill('#pm_description', { theme: 'snow' });

  function openModal(mode = 'create') {
    modal.style.display = 'flex';
    if (mode === 'create') {
      pmTitleHeader.textContent = 'Add New Product';
      pmForm.reset();
      quill.setText('');
      pmId.value = '';
      imagesPreview.innerHTML = '';
    }
  }
  function closeModal() { modal.style.display = 'none'; }

  pmCancel?.addEventListener('click', closeModal);

  // image previews
  imagesInput?.addEventListener('change', (e) => {
    imagesPreview.innerHTML = '';
    Array.from(e.target.files).forEach(file => {
      const url = URL.createObjectURL(file);
      const imgWrap = document.createElement('div');
      imgWrap.className = 'relative';
      imgWrap.innerHTML = `
        <img src="${url}" class="w-full h-24 object-cover rounded-md" />
        <button type="button" class="absolute top-1 right-1 bg-black/60 text-white rounded-full px-2 text-xs remove-btn">x</button>
      `;
      imagesPreview.appendChild(imgWrap);
      imgWrap.querySelector('.remove-btn').addEventListener('click', () => {
        // remove file from input (rebuild FileList)
        const dt = new DataTransfer();
        Array.from(imagesInput.files).forEach(f => { if (f !== file) dt.items.add(f); });
        imagesInput.files = dt.files;
        imgWrap.remove();
      });
    });
  });

  // safe JSON parse helper: check content-type first
  async function safeFetchJson(url, options) {
    const res = await fetch(url, options);
    const ct = res.headers.get('content-type') || '';
    if (!res.ok) {
      // try to parse json error
      if (ct.includes('application/json')) {
        const j = await res.json();
        throw new Error(j.message || 'Request failed');
      } else {
        const text = await res.text();
        throw new Error(text || res.statusText);
      }
    }
    if (ct.includes('application/json')) return res.json();
    // if not json, return text (avoid unexpected token error)
    return res.text();
  }

  // submit product (create or update)
  pmForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = pmId.value;
    const payloadUrl = id ? `/api/products/${id}` : '/api/products';
    const method = id ? 'PUT' : 'POST';

    const formData = new FormData();
    formData.append('title', document.getElementById('pm_title').value);
    formData.append('sku', document.getElementById('pm_sku').value);
    formData.append('description', quill.root.innerHTML);
    formData.append('category', document.getElementById('pm_category').value);
    formData.append('status', document.getElementById('pm_status').value);
    formData.append('price', document.getElementById('pm_price').value);
    formData.append('stock', document.getElementById('pm_stock').value);
    // tags
    formData.append('tags', document.getElementById('pm_tags_input')?.value || '');

    // append images
    Array.from(imagesInput.files || []).forEach((file, idx) => {
      formData.append('images', file, file.name);
    });

    try {
      const res = await safeFetchJson(payloadUrl, { method, body: formData });
      // res expected to be JSON with product id and image urls
      console.log('Saved', res);
      // refresh products table (implement loadProducts)
      await loadProducts();
      closeModal();
    } catch (err) {
      alert('Error saving product: ' + err.message);
      console.error(err);
    }
  });

  // placeholder loadProducts — replace with actual implementation
  async function loadProducts() {
    // fetch list and render table; keep minimal here
    const tbody = document.getElementById('products-table-body');
    tbody.innerHTML = '';
    try {
      const products = await safeFetchJson('/api/products', { method: 'GET' });
      products.forEach(p => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td class="p-4">${p.title}</td>
          <td class="p-4">${p.sku}</td>
          <td class="p-4">$${p.price}</td>
          <td class="p-4">${p.stock}</td>
          <td class="p-4">${p.status}</td>
          <td class="p-4">
            <button onclick="editProduct('${p.id}')" class="text-blue-600 mr-2">Edit</button>
            <button onclick="deleteProduct('${p.id}')" class="text-red-600">Delete</button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    } catch (err) {
      console.error('loadProducts error', err);
    }
  }

  // initial load
  loadProducts();
});
