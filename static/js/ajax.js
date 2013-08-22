
$(document).ready(function() {
    "use strict";
    var status = $("#status");
    var results = $("#results");
    var statusHeader = $('#status-header');
    var statusSpinner = $('#status-spinner');
    var statusMessage = $('#status-message');


    function setStatus(header, message) {
        statusHeader.text(header);
        statusMessage.text(message);
    }

    function getData(path, callback) {
        $.getJSON(path, function(data){
        if (data['status'] !== 'done') {
            setStatus(data['header'], data['message']);
            if (data['status'] !== 'error') {
                setTimeout(function() {getData(path, callback);}, 500);
            }
            else {
                statusSpinner.spin(false);
                statusSpinner.remove();
            }
        }
        else {
                status.hide();
                status.remove();
                results.removeClass('hidden');
                callback(data['data']);
            }
        });
    }
    statusSpinner.spin()
});
