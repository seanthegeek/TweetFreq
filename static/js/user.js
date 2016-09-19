$(document).ready(function() {
    "use strict";

    function processData(data) {
        $("#total").text(data['stats']['total']['formatted']);
        $("#avg").text(data['stats']['avg_per_day']['formatted']);
        $("#max").text(data['stats']['max_per_day']['formatted']);
        $("#start").text(data['start']['timestamp']);
        $("#end").text(data['end']['timestamp']);
        $("#created").text(data['created']);
        $("#expires").text(data['expires']);

        // Load words
        var searchBase = 'https://twitter.com/search?mode=realtime&q=';
        var searchURL;
        var date;
        var word;
        var tr;
        var words = data['words'];
        for (var i=0; i<data['dates'].length; i++){
            date = data['dates'][i];
            if (i === data['dates'].length-1) {
                searchURL = searchBase + encodeURIComponent('from:'+ userName+ ' since:'+date[0]);
            }
            else {
                searchURL = searchBase + encodeURIComponent('from:'+ userName+ ' since:'+date[0]+ ' until:'+data['dates'][i+1][0]);
            }
            tr = "<tr><td><a target='_blank' href='"+searchURL+"'>"+date[0]+"</a></td><td>"+date[1]+"</td></tr>";
            $("#dates-body").append(tr);
        }
        updateWordcloud(words);

        $("#dates").dataTable();

        for (var i=0; i<data['words'].length; i++){
            word = data['words'][i];
            searchURL = searchBase + encodeURIComponent('from:'+ userName+ ' '+word[0]);
            tr = "<tr><td>"+(i+1)+"</td><td><a target='_blank' href='"+searchURL+"'>"+word[0]+"</a></td><td>"+word[1]+"</td></tr>";
            $("#words-body").append(tr);
        }
        $("#words").dataTable();

        $('#chart').highcharts({
            chart: {
                zoomType: 'x',
            },
            title: {
                text: 'Tweet frequency per day for ' + userName
            },
            subtitle: {
                text: "TweetFreq.net"
            },
            xAxis: {
                type: 'datetime',
                maxZoom: 14 * 24 * 3600000, // fourteen days
                title: {
                    text: 'Dates'
                }
            },
            yAxis: {
                title: {
                    text: 'Number of tweets',
                    min: 1
                }
            },
            tooltip: {
                shared: true
            },
            legend: {
                enabled: false
            },
            plotOptions: {
                area: {
                    fillColor: {
                        linearGradient: { x1: 0, y1: 0, x2: 0, y2: 1},
                        stops: [
                            [0, Highcharts.getOptions().colors[0]],
                            [1, Highcharts.Color(Highcharts.getOptions().colors[0]).setOpacity(0).get('rgba')]
                        ]
                    },
                    lineWidth: 1,
                    marker: {
                        enabled: false
                    },
                    shadow: false,
                    states: {
                        hover: {
                            lineWidth: 1
                        }
                    },
                    threshold: null
                }
            },

            series: [{
                type: 'area',
                name: 'Tweets',
                data: data['dates'].map(function(d) {d[0]=new Date(d[0]).getTime(); return d;})
            }]
        });
    }

    $.getData("/u/" + userName + ".json", processData);
});
