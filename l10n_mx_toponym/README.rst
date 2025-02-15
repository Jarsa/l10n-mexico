===================
Toponyms for Mexico
===================

.. !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
   !! This file is generated by oca-gen-addon-readme !!
   !! changes will be overwritten.                   !!
   !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

.. |badge1| image:: https://img.shields.io/badge/maturity-Beta-yellow.png
    :target: https://odoo-community.org/page/development-status
    :alt: Beta
.. |badge2| image:: https://img.shields.io/badge/licence-AGPL--3-blue.png
    :target: http://www.gnu.org/licenses/agpl-3.0-standalone.html
    :alt: License: AGPL-3
.. |badge3| image:: https://img.shields.io/badge/github-OCA%2Fl10n--mexico-lightgray.png?logo=github
    :target: https://github.com/OCA/l10n-mexico/tree/15.0/l10n_mx_toponym
    :alt: OCA/l10n-mexico
.. |badge4| image:: https://img.shields.io/badge/weblate-Translate%20me-F47D42.png
    :target: https://translation.odoo-community.org/projects/l10n-mexico-15-0/l10n-mexico-15-0-l10n_mx_toponym
    :alt: Translate me on Weblate
.. |badge5| image:: https://img.shields.io/badge/runbot-Try%20me-875A7B.png
    :target: https://runbot.odoo-community.org/runbot/193/15.0
    :alt: Try me on Runbot

|badge1| |badge2| |badge3| |badge4| |badge5| 

This module adds toponyms for Mexico.

It allow you to ease capture for contact using zip code and get the following information:

* Colony
* Colony Code
* Locality
* City
* State

It creates a partner View related to country in order to show the fields only if Mexico is the company country.

Also import the catalogs from SAT.

**Table of contents**

.. contents::
   :local:

Configuration
=============

#. Go to *Settings / Users & Companies / Companies*.
#. Select the Mexican Company
#. Be sure that you select Mexico as country.

#. Go to *Contacts / Configuration / Localization / Countries*.
#. Locate the Mexico.
#. Be sure Enfoce cities is active.
#. Be sure that the Input View is 'l10n_mx_toponym.res.partner.address.form'

Usage
=====

#. Access a partner record
#. Fill the field *Location completion*
#. Information about country, state, city, colony, colony code, locality and zip will be filled automatically

Bug Tracker
===========

Bugs are tracked on `GitHub Issues <https://github.com/OCA/l10n-mexico/issues>`_.
In case of trouble, please check there if your issue has already been reported.
If you spotted it first, help us smashing it by providing a detailed and welcomed
`feedback <https://github.com/OCA/l10n-mexico/issues/new?body=module:%20l10n_mx_toponym%0Aversion:%2015.0%0A%0A**Steps%20to%20reproduce**%0A-%20...%0A%0A**Current%20behavior**%0A%0A**Expected%20behavior**>`_.

Do not contact contributors directly about support or help with technical issues.

Credits
=======

Authors
~~~~~~~

* Jarsa

Contributors
~~~~~~~~~~~~

* Alan Ramos (Jarsa)

Maintainers
~~~~~~~~~~~

This module is maintained by the OCA.

.. image:: https://odoo-community.org/logo.png
   :alt: Odoo Community Association
   :target: https://odoo-community.org

OCA, or the Odoo Community Association, is a nonprofit organization whose
mission is to support the collaborative development of Odoo features and
promote its widespread use.

.. |maintainer-alan196| image:: https://github.com/alan196.png?size=40px
    :target: https://github.com/alan196
    :alt: alan196

Current `maintainer <https://odoo-community.org/page/maintainer-role>`__:

|maintainer-alan196| 

This module is part of the `OCA/l10n-mexico <https://github.com/OCA/l10n-mexico/tree/15.0/l10n_mx_toponym>`_ project on GitHub.

You are welcome to contribute. To learn how please visit https://odoo-community.org/page/Contribute.
