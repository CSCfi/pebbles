app.factory('DesktopNotifications', ['webNotification', 'localStorageService',
                    function(webNotification,   localStorageService) {
 
   /* Send desktop notifications for instance lifetime and service level notiications */

    return{

        /* The array behaves as a queue data-structure.
         * Remove the level after showing the notification after specified time */
        notification_levels : [
            Infinity, // START
            900,  // 15 Minutes
            300  // 5 Minutes
        ],

        /* Send desktop notifications after desired time levels.
        * All time levels would be denoted in Seconds
        * START will always be Infinity, If you want to send one at the END, use 0 */

        /* The main function which needs the list of instances */
        notifyInstanceLifetime : function(instance_list) {
            var instance_index = 0;
            var notification_queue;
            while(instance_index < instance_list.length){
                var instance = instance_list[instance_index];
                notification_queue = localStorageService.get(instance.name);
                if (!notification_queue){
                    notification_queue = this.notification_levels.slice(0);
                }
                if(notification_queue.length > 0){
                    var time_boundary = this._getTimeBoundaryForNotification(notification_queue);
                    if (instance.lifetime_left < time_boundary){
                        var notification_title;
                        var notification_message;
                        var instance_lifetime_text = this._secondsToMinutesText(instance.lifetime_left);
                        if(time_boundary == Infinity){
                            notification_title = 'Your instance is now running';
                            notification_message = 'Total time left is ' + instance_lifetime_text;
                        }
                        else{
                            notification_title = 'WARNING! Instance Expiring in ' + instance_lifetime_text;
                            notification_message = 'Download the work files to your local machine.';
                        }
                        notification_queue = this._getUpdatedQueueForTimeWindow(instance.lifetime_left, notification_queue);
                        webNotification.showNotification(notification_title, {
                            body: notification_message,
                            autoClose: 10000
                        }, function onShow(error, hide) {
                            if (error) {
                                console.log('Unable to show warnings for instance expiration. Check manually ' + error.message);
                            }
                            localStorageService.set(instance.name, notification_queue)
                       });
                    }
                 }
                 instance_index++;
            }
        },

        _secondsToMinutesText : function(secs){
            var time_text;
            var mins = Math.round(secs / 60);
            if(mins > 60){
                var hours = parseInt(mins / 60);
                var rem_mins = mins - (hours * 60);
                time_text = hours + 'H ' + rem_mins + 'M';
            }
            else{
                time_text = mins + ' Mins'; 
            }
            return time_text;
        },

        /* Get the first element of the queue which serves as the current limit */
        _getTimeBoundaryForNotification : function(notification_queue){
            var boundary;
            boundary  = notification_queue[0];
            return boundary;
        },

        /* Update the notification queue based on the current time window.
         * Remove the time level for which the notification has already been displayed */
        _getUpdatedQueueForTimeWindow : function(time, notification_queue){
            if (notification_queue.length > 0){
                if(time <= notification_queue[0]){
                    notification_queue.shift();
                }
            }
            return notification_queue;
        },

        notifyNotifications : function(notification) {
            webNotification.showNotification(notification.subject, {
                 body: notification.message,
                 autoClose: 10000
            }, function onShow(error, hide) {
               if (error) {
                  console.log('Unable to show notifications. Check manually ' + error.message);
               }
            });
        },

    };
}]);
