This directory contains the EcmaScript frontend code of Kubernetes Operational View and is only needed during build time.

Requirements: Node.js 20 or newer (tested with Node 24).

The JavaScript application bundle (webpack 5) will be generated to ``kube_ops_view/static/build/app-<hash>.js`` by running:

.. code-block:: bash

    $ npm ci
    $ npm run build

The build output is not tracked in Git. The Flask app serves the first ``app*.js`` file found in ``kube_ops_view/static/build``,
so the webpack config makes sure that only a single bundle file is emitted.

Frontend development is supported by watching the source code and continuously recompiling the webpack
(development build to ``kube_ops_view/static/build/app.js``):

.. code-block:: bash

    $ npm start

The same commands work on Windows (PowerShell/cmd), there are no platform specific scripts anymore.

Run the linter with ``npm run lint``.

Rendering library
=================

The UI is drawn with `PixiJS <https://pixijs.com/>`_ v8 (``pixi.js``) and the CRT theme uses ``pixi-filters``.
The code was migrated from PixiJS v4 with these changes worth knowing:

* Only ``Container`` may have children in PixiJS v8: ``Cluster``, ``Node``, ``Pod``, ``SelectBox`` and ``Tooltip``
  extend ``Container`` and draw on an inner ``Graphics`` (``this.gfx``).
* Drawing uses the v8 ``rect().fill().stroke()`` API (the v4 ``lineStyle()``/``beginFill()`` API is deprecated in v8
  and does not stroke shapes anymore).
* The renderer is created asynchronously (``await autoDetectRenderer()``), therefore ``App.run()`` is ``async``.
* Ticker callbacks receive the ticker (``ticker.deltaTime``) instead of the delta.
* ``#renderer=canvas`` selects the Canvas2D renderer. Filters (hover brightness, search dimming, most themes) are not
  supported by it and are skipped, WebGL is the recommended (default) renderer.

There is no Babel step: the bundle targets browsers with ES2020 support (as PixiJS v8 does).
