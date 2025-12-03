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
  const sourceField = container.querySelector('input[name="source"]');
  const targetField = container.querySelector('input[name="target"]');
  const sourceList = container.querySelector('[data-merge-source-list]');
  const emptySources = container.querySelector('[data-merge-empty-sources]');
  const liveRegion = container.querySelector('[data-merge-live]');
  const labelLookup = new Map();

  container.querySelectorAll('[data-merge-source-row]').forEach((row) => {
    const id = row.dataset.mergeObjectId;
    if (!id) {
      return;
    }
    labelLookup.set(id.toString(), row.dataset.mergeObjectLabel || '');
  });

  const normalizeList = (values) => {
    const seen = new Set();
    const normalized = [];
    values.forEach((value) => {
      const trimmed = (value || '').toString().trim();
      if (!trimmed || seen.has(trimmed)) {
        return;
      }
      seen.add(trimmed);
      normalized.push(trimmed);
    });
    return normalized;
  };

  const getState = () => {
    const targetId = targetField ? targetField.value : '';
    const selectedIds = normalizeList((idsField && idsField.value ? idsField.value.split(',') : []));
    let sources = selectedIds.filter((id) => id !== targetId);

    const primarySource = sourceField ? sourceField.value : '';
    if (primarySource && primarySource !== targetId) {
      sources = [primarySource, ...sources.filter((id) => id !== primarySource)];
    }

    return { targetId, sources };
  };

  const renderSources = (sources) => {
    if (!sourceList) {
      return;
    }
    const primaryLabel = sourceList.dataset.primaryLabel || 'Primary';
    const removeLabel = sourceList.dataset.removeLabel || 'Remove';
    sourceList.innerHTML = '';
    if (!sources.length) {
      if (emptySources) {
        emptySources.removeAttribute('hidden');
        sourceList.appendChild(emptySources);
      }
      return;
    }

    if (emptySources) {
      emptySources.setAttribute('hidden', 'hidden');
    }

    sources.forEach((id, index) => {
      const row = document.createElement('li');
      row.className = 'w3-padding-small w3-border-bottom';
      const label = document.createElement('span');
      const labelText = labelLookup.get(id) || '';
      label.textContent = labelText ? `${labelText} (ID ${id})` : `ID ${id}`;
      row.appendChild(label);
      if (index === 0) {
        const badge = document.createElement('span');
        badge.className = 'w3-tag w3-round w3-blue w3-margin-left';
        badge.textContent = primaryLabel;
        row.appendChild(badge);
      }
      const removeButton = document.createElement('button');
      removeButton.type = 'button';
      removeButton.className = 'w3-button w3-small w3-light-grey w3-round w3-margin-left';
      removeButton.dataset.mergeRemoveSource = id;
      removeButton.innerHTML = `<span class="fa fa-times" aria-hidden="true"></span> <span class="w3-margin-left">${removeLabel}</span>`;
      removeButton.addEventListener('click', () => handleSourceRemoval(id));
      row.appendChild(removeButton);
      sourceList.appendChild(row);
    });
  };

  const announce = (message) => {
    if (liveRegion) {
      liveRegion.textContent = message;
    }
  };

  const syncFields = (state) => {
    const ids = normalizeList([state.targetId, ...state.sources.filter((id) => id !== state.targetId)]);
    if (idsField) {
      idsField.value = ids.join(',');
    }
    if (targetField) {
      targetField.value = state.targetId || '';
    }
    if (sourceField) {
      sourceField.value = state.sources[0] || '';
    }
    renderSources(state.sources);
  };

  const navigateWithState = (state) => {
    syncFields(state);
    const url = new URL(window.location.href);
    if (state.targetId) {
      url.searchParams.set('target', state.targetId);
    } else {
      url.searchParams.delete('target');
    }
    const primarySource = state.sources[0] || '';
    if (primarySource) {
      url.searchParams.set('source', primarySource);
    } else {
      url.searchParams.delete('source');
    }
    if (idsField && idsField.value) {
      url.searchParams.set('ids', idsField.value);
    } else {
      url.searchParams.delete('ids');
    }
    window.location.href = url.toString();
  };

  const handleSourceRemoval = (id) => {
    const state = getState();
    state.sources = state.sources.filter((sourceId) => sourceId !== id);
    announce(`Removed source ${id}`);
    navigateWithState(state);
  };

  const handleSelection = (role, pk) => {
    if (!pk) {
      return;
    }
    const state = getState();
    const candidateId = pk.toString();
    if (role === 'target') {
      const previousTarget = state.targetId;
      state.targetId = candidateId;
      state.sources = state.sources.filter((id) => id !== candidateId);
      if (previousTarget && previousTarget !== candidateId) {
        state.sources = [previousTarget, ...state.sources.filter((id) => id !== previousTarget)];
      }
      announce(`Set target to ${candidateId}`);
    } else {
      state.sources = [candidateId, ...state.sources.filter((id) => id !== candidateId && id !== state.targetId)];
      announce(`Added source ${candidateId}`);
    }
    navigateWithState(state);
  };

  container.querySelectorAll('[data-merge-set-role]').forEach((button) => {
    button.addEventListener('click', (event) => {
      event.preventDefault();
      const role = button.dataset.mergeSetRole;
      const pk = button.dataset.mergeObjectId;
      if (!role || !pk) {
        return;
      }
      handleSelection(role, pk);
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
      resultsContainer.innerHTML = '<p class="w3-padding w3-text-grey">No candidates found.</p>';
      return;
    }

    const fragment = document.createDocumentFragment();
    payload.results.forEach((item) => {
      const column = document.createElement('div');
      column.className = 'w3-col l4 m6 w3-margin-bottom';

      const card = document.createElement('article');
      card.className = 'w3-card w3-white w3-round-large w3-padding-large';

      const header = document.createElement('header');
      const title = document.createElement('h3');
      title.textContent = `${item.candidate.label || 'Candidate'} (ID ${item.candidate.pk})`;
      header.appendChild(title);
      card.appendChild(header);

      if (Array.isArray(item.preview) && item.preview.length) {
        const previewList = document.createElement('ul');
        previewList.className = 'w3-ul w3-small';
        item.preview.forEach((row) => {
          const li = document.createElement('li');
          li.innerHTML = `<strong>${row.field}:</strong> ${row.value || ''}`;
          previewList.appendChild(li);
        });
        card.appendChild(previewList);
      }

      const actions = document.createElement('div');
      actions.className = 'w3-margin-top';

      const targetButton = document.createElement('button');
      targetButton.type = 'button';
      targetButton.className = 'button w3-button w3-round w3-blue w3-margin-right';
      targetButton.textContent = 'Use as target';
      targetButton.addEventListener('click', () => {
        if (item.candidate && item.candidate.pk) {
          labelLookup.set(item.candidate.pk.toString(), item.candidate.label || '');
        }
        handleSelection('target', item.candidate.pk);
      });
      actions.appendChild(targetButton);

      const sourceButton = document.createElement('button');
      sourceButton.type = 'button';
      sourceButton.className = 'button w3-button w3-round w3-border';
      sourceButton.textContent = 'Use as source';
      sourceButton.addEventListener('click', () => {
        if (item.candidate && item.candidate.pk) {
          labelLookup.set(item.candidate.pk.toString(), item.candidate.label || '');
        }
        handleSelection('source', item.candidate.pk);
      });
      actions.appendChild(sourceButton);

      card.appendChild(actions);
      column.appendChild(card);
      fragment.appendChild(column);
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
          resultsContainer.innerHTML = '<p class="w3-padding w3-text-grey">Enter a search term to continue.</p>';
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
        resultsContainer.innerHTML = '<p class="w3-padding w3-text-grey">Searching…</p>';
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
            resultsContainer.innerHTML = '<p class="w3-padding w3-text-red">Unable to load merge candidates.</p>';
          }
        });
    });
  }

  renderSources(getState().sources);
})();
