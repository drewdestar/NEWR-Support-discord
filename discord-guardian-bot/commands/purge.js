const { SlashCommandBuilder, PermissionFlagsBits, EmbedBuilder } = require('discord.js');

module.exports = {
    data: new SlashCommandBuilder()
        .setName('purge')
        .setDescription('Delete multiple messages at once')
        .addIntegerOption(option =>
            option.setName('amount')
                .setDescription('Number of messages to delete (1-100)')
                .setRequired(true)
                .setMinValue(1)
                .setMaxValue(100)
        )
        .setDefaultMemberPermissions(PermissionFlagsBits.ManageMessages),
    
    async execute(interaction, client, config) {
        const amount = interaction.options.getInteger('amount');
        
        // Check permissions
        if (!interaction.member.permissions.has(PermissionFlagsBits.ManageMessages)) {
            return interaction.reply({ 
                content: '❌ You don\'t have permission to manage messages!', 
                ephemeral: true 
            });
        }
        
        if (!interaction.channel.isTextBased()) {
            return interaction.reply({ 
                content: '❌ This command can only be used in text channels!', 
                ephemeral: true 
            });
        }
        
        try {
            await interaction.deferReply({ ephemeral: true });
            
            const deletedMessages = await interaction.channel.bulkDelete(amount + 1, true);
            
            const embed = new EmbedBuilder()
                .setColor(0x2ECC71)
                .setTitle('🗑️ Messages Purged')
                .setDescription(`Successfully deleted **${deletedMessages.size - 1}** messages!`)
                .addFields(
                    { name: 'Channel', value: `<#${interaction.channel.id}>`, inline: true },
                    { name: 'Moderator', value: `${interaction.user.tag}`, inline: true }
                )
                .setTimestamp();
            
            await interaction.editReply({ embeds: [embed] });
            
            // Delete the response after 5 seconds
            setTimeout(async () => {
                try {
                    await interaction.deleteReply();
                } catch (error) {
                    console.error('Error deleting purge response:', error);
                }
            }, 5000);
            
        } catch (error) {
            console.error('Error purging messages:', error);
            
            if (error.code === 50034) {
                await interaction.editReply({ 
                    content: '❌ Cannot delete messages older than 14 days!', 
                    ephemeral: true 
                });
            } else {
                await interaction.editReply({ 
                    content: '❌ Failed to delete messages! Make sure I have the necessary permissions.', 
                    ephemeral: true 
                });
            }
        }
    }
};
