(function () {
  const container = document.querySelector('[data-merge-admin]');
  if (!container) {
    return;
  }

  const searchForm = container.querySelector('[data-merge-search-form]');
  const resultsContainer = container.querySelector('[data-merge-results]');
  const searchUrl = container.dataset.searchUrl;
  const modelLabel = container.dataset.modelLabel;
  const idsField = container.querySelector('input[name="selected_ids"]');

  const updateLocation = (role, pk) => {
    const url = new URL(window.location.href);
    if (pk) {
      url.searchParams.set(role, pk);
    } else {
      url.searchParams.delete(role);
    }
    if (idsField && idsField.value) {
      url.searchParams.set('ids', idsField.value);
    }
    window.location.href = url.toString();
  };

  container.querySelectorAll('[data-merge-set-role]').forEach((button) => {
    button.addEventListener('click', (event) => {
      event.preventDefault();
      const role = button.dataset.mergeSetRole;
      const pk = button.dataset.mergeObjectId;
      if (!role || !pk) {
        return;
      }
      updateLocation(role, pk);
    });
  });

  const escapeSelector = (value) => {
    if (window.CSS && typeof window.CSS.escape === 'function') {
      return window.CSS.escape(value);
    }
    return value.replace(/([^a-zA-Z0-9_-])/g, '\\$1');
  };

  const toggleManualInputs = () => {
    container.querySelectorAll('[data-merge-strategy-container]').forEach((wrapper) => {
      const select = wrapper.querySelector('select');
      if (!select) {
        return;
      }
      const name = select.name || '';
      const fieldName = name.replace(/^strategy__/, '');
      const manualWrapper = container.querySelector(
        `[data-merge-manual-field="${escapeSelector(fieldName)}"]`
      );
      if (!manualWrapper) {
        return;
      }
      if (select.value === 'user_prompt') {
        manualWrapper.removeAttribute('hidden');
      } else {
        manualWrapper.setAttribute('hidden', 'hidden');
      }
    });
  };

  container.addEventListener('change', (event) => {
    if (event.target && event.target.matches('[data-merge-strategy-container] select')) {
      toggleManualInputs();
    }
  });
  toggleManualInputs();

  const renderResults = (payload) => {
    if (!resultsContainer) {
      return;
    }
    if (!payload || !Array.isArray(payload.results) || payload.results.length === 0) {
      resultsContainer.innerHTML = '<p class="merge-admin__notice">No candidates found.</p>';
      return;
    }

    const fragment = document.createDocumentFragment();
    payload.results.forEach((item) => {
      const card = document.createElement('article');
      card.className = 'merge-admin__card';

      const header = document.createElement('header');
      const title = document.createElement('h3');
      title.textContent = `${item.candidate.label || 'Candidate'} (ID ${item.candidate.pk})`;
      header.appendChild(title);
      card.appendChild(header);

      if (Array.isArray(item.preview) && item.preview.length) {
        const previewList = document.createElement('ul');
        previewList.className = 'merge-admin__preview';
        item.preview.forEach((row) => {
          const li = document.createElement('li');
          li.innerHTML = `<strong>${row.field}:</strong> ${row.value || ''}`;
          previewList.appendChild(li);
        });
        card.appendChild(previewList);
      }

      const actions = document.createElement('div');
      actions.className = 'merge-admin__card-actions';

      const targetButton = document.createElement('button');
      targetButton.type = 'button';
      targetButton.className = 'button';
      targetButton.textContent = 'Use as target';
      targetButton.addEventListener('click', () => updateLocation('target', item.candidate.pk));
      actions.appendChild(targetButton);

      const sourceButton = document.createElement('button');
      sourceButton.type = 'button';
      sourceButton.className = 'button';
      sourceButton.textContent = 'Use as source';
      sourceButton.addEventListener('click', () => updateLocation('source', item.candidate.pk));
      actions.appendChild(sourceButton);

      card.appendChild(actions);
      fragment.appendChild(card);
    });

    resultsContainer.innerHTML = '';
    resultsContainer.appendChild(fragment);
  };

  if (searchForm && searchUrl) {
    searchForm.addEventListener('submit', (event) => {
      event.preventDefault();
      const formData = new FormData(searchForm);
      const query = (formData.get('query') || '').toString().trim();
      if (!query) {
        if (resultsContainer) {
          resultsContainer.innerHTML = '<p class="merge-admin__notice">Enter a search term to continue.</p>';
        }
        return;
      }

      const params = new URLSearchParams();
      params.set('model_label', modelLabel);
      params.set('query', query);
      const threshold = (formData.get('threshold') || '').toString().trim();
      if (threshold) {
        params.set('threshold', threshold);
      }

      if (resultsContainer) {
        resultsContainer.innerHTML = '<p class="merge-admin__notice">Searching…</p>';
      }

      fetch(`${searchUrl}?${params.toString()}`)
        .then((response) => {
          if (!response.ok) {
            throw new Error('Request failed');
          }
          return response.json();
        })
        .then((payload) => {
          renderResults(payload);
        })
        .catch(() => {
          if (resultsContainer) {
            resultsContainer.innerHTML = '<p class="merge-admin__error">Unable to load merge candidates.</p>';
          }
        });
    });
  }
})();
