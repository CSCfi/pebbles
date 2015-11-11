// create a custom directive for displaying instance lifetime in human readable format
app.directive('lifetime', function () {
        function link(scope, element, attributes) {

            // Here we have to use a attribute change listener. The first time 'link' is fired
            // we might not have the data loaded to scope yet.
            attributes.$observe('value', function (newValue) {

                var nSecs = parseInt(newValue, 10);
                // see if we are dealing with infinite lifetime
                if (nSecs == 0 && typeof(attributes.maximumLifetime) != 'undefined' && attributes.maximumLifetime == 0) {
                    element.text('infinite');
                }
                else {
                    var days = Math.floor(nSecs / (3600 * 24));
                    var secsLeft = nSecs - days * 3600 * 24;

                    var hours = Math.floor(secsLeft / 3600);
                    secsLeft -= hours * 3600;

                    var minutes = Math.floor(secsLeft / 60);
                    secsLeft -= minutes * 60;

                    var seconds = secsLeft;

                    var timeStr;
                    if (days == 0 && hours == 0 && minutes == 0) {
                        timeStr = seconds + ' s';
                    }
                    else if (days == 0 && hours == 0 && minutes < 5) {
                        timeStr = minutes + 'm ' + seconds + ' s';
                    }
                    else {
                        timeStr = hours + 'h ' + minutes + 'm';
                        if (days) {
                            timeStr = days + 'd ' + timeStr;
                        }
                    }
                    element.text(timeStr);
                }
            });
        }

        return {
            restrict: 'E',
            link: link
        };
    }
);
