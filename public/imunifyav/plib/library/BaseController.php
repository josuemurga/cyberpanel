<?php

namespace Imunify360;


class BaseController extends \pm_Controller_Action
{
    protected function commonAppends()
    {
        // Plesk prototype.js causes errors when webpack trying to load modules
        $this->view->headScript()->appendScript('delete Array.prototype.entries;');
        $this->view->headScript()->appendScript('
            HTMLDivElement.prototype.__originalRemove = HTMLDivElement.prototype.remove;
            HTMLDivElement.prototype.remove = function() {
                if (this?.parentNode) {
                    this.__originalRemove();
                }
            };');
    }
}
